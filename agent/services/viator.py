# agent/services/viator.py - ENHANCED CACHING VERSION
import os
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import List, Dict, Optional
from functools import wraps
import json
from django.core.cache import cache, caches
import hashlib
from django.conf import settings
import logging

load_dotenv()
logger = logging.getLogger(__name__)


class ViatorAPIError(Exception):
    """Custom exception for Viator API errors."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Viator API error {status_code}: {message}")


def retry_on_rate_limit(max_retries=3, backoff_factor=2):
    """Retry decorator for handling 429 rate limits."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ViatorAPIError as e:
                    if e.status_code == 429 and attempt < max_retries - 1:
                        wait_time = backoff_factor ** attempt
                        logger.warning(f"[Viator] Rate limit hit, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise
            return None
        return wrapper
    return decorator


class ViatorService:
    BASE_URL = os.getenv("VIATOR_BASE_URL", "https://api.viator.com/partner")
    AFFILIATE_ID = os.getenv("VIATOR_AFFILIATE_ID", "")
    HEADERS = {
        "exp-api-key": os.getenv("VIATOR_API_KEY"),
        "Accept": "application/json;version=2.0",
        "Content-Type": "application/json",
        "Accept-Language": "en-US"
    }
    
    # Cache configuration
    CACHE_TTL_SEARCH = 60 * 60      # 60 minutes — tours change very slowly
    CACHE_TTL_DESTINATIONS = 60 * 60 * 24  # 24 hours
    CACHE_TTL_PRODUCT_DETAILS = 60 * 30  # 30 minutes
    CACHE_TTL_AVAILABILITY = 60 * 10  # 10 minutes (availability changes faster)

    def __init__(self):
        if not self.HEADERS["exp-api-key"]:
            raise ValueError("Missing VIATOR_API_KEY in environment variables. Please set VIATOR_API_KEY in your .env file.")
        
        self.destinations_cache = None
        # Use api_cache for faster responses
        self.api_cache = caches['api_cache']

    # ================================================================
    # API REQUEST WRAPPER
    # ================================================================
    @retry_on_rate_limit()
    def _make_request(self, method: str, endpoint: str,
                      params: Dict = None, json: Dict = None) -> Optional[Dict]:
        """Make a Viator API request with error handling and retries."""
        url = f"{self.BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            logger.debug(f"[Viator] {method} {endpoint}")
            response = requests.request(
                method, url,
                headers=self.HEADERS,
                params=params,
                json=json,
                timeout=30
            )
            
            if not response.ok:
                logger.error(f"[Viator] API error {response.status_code}: {response.text[:200]}")
                raise ViatorAPIError(response.status_code, response.text)
            
            return response.json()

        except requests.exceptions.Timeout:
            logger.error(f"[Viator] Timeout for endpoint '{endpoint}'")
            raise ViatorAPIError(408, f"Request timeout for endpoint '{endpoint}'")
        except ViatorAPIError:
            raise
        except requests.exceptions.RequestException as e:
            status_code = e.response.status_code if e.response else 0
            message = e.response.text if e.response else str(e)
            logger.error(f"[Viator] Request failed: {message[:200]}")
            raise ViatorAPIError(status_code, message)

    # ================================================================
    # DESTINATIONS - CACHED
    # ================================================================
    def get_destinations(self) -> List[Dict]:
        """Get all Viator destinations - cached for 24 hours."""
        # Check in-memory cache first (fastest)
        if self.destinations_cache is not None:
            logger.debug("[Viator] Using in-memory destinations cache")
            return self.destinations_cache

        # Check Redis cache
        cache_key = "viator:destinations"
        cached = self.api_cache.get(cache_key)
        if cached is not None:
            logger.info("[Cache HIT] Viator destinations")
            self.destinations_cache = cached
            return cached

        logger.info("[Cache MISS] Fetching Viator destinations from API...")
        response = self._make_request("GET", "destinations")
        
        # Parse response (handle different formats)
        if isinstance(response, list):
            destinations = response
        elif isinstance(response, dict):
            if "destinations" in response:
                destinations = response["destinations"]
            elif "data" in response and isinstance(response["data"], dict) and "destinations" in response["data"]:
                destinations = response["data"]["destinations"]
            elif "data" in response and isinstance(response["data"], list):
                destinations = response["data"]
            else:
                raise ViatorAPIError(500, f"Unexpected /destinations format: {response}")
        else:
            raise ViatorAPIError(500, "Unexpected destination response type.")

        # Cache for 24 hours
        self.api_cache.set(cache_key, destinations, timeout=self.CACHE_TTL_DESTINATIONS)
        self.destinations_cache = destinations
        logger.info(f"[Viator] Cached {len(destinations)} destinations for 24h")
        return destinations

    def resolve_destination(self, name: str) -> str:
        """Resolve destination name to its Viator ID - uses cached destinations."""
        # Build cache key for resolved destination
        cache_key = f"viator:dest_id:{name.lower().strip()}"
        
        # Check if we've already resolved this destination
        cached_id = self.api_cache.get(cache_key)
        if cached_id:
            logger.debug(f"[Cache HIT] Destination ID for '{name}': {cached_id}")
            return cached_id
        
        # Resolve from destinations list (which is cached)
        destinations = self.get_destinations()
        name_lower = name.lower()

        # Exact match first
        match = next((d for d in destinations if d.get("name", "").lower() == name_lower), None)
        
        # Partial match fallback
        if not match:
            match = next((d for d in destinations if name_lower in d.get("name", "").lower()), None)

        if not match:
            raise ViatorAPIError(404, f"Destination '{name}' not found in Viator database.")
        
        dest_id = int(match.get("destinationId"))
        
        # Cache the resolved ID for 24 hours
        self.api_cache.set(cache_key, dest_id, timeout=self.CACHE_TTL_DESTINATIONS)
        logger.info(f"[Viator] Resolved '{name}' -> ID {dest_id}")
        return dest_id

    # ================================================================
    # TOUR SEARCH - ENHANCED CACHING
    # ================================================================
    def search_tours(self, query: Optional[str], destination: str,
                     start_date: Optional[str] = None, page_size: int = 5) -> List[Dict]:
        """Search for tours — fully cached by destination + date range + page_size."""
        
        # Normalize inputs
        destination_norm = destination.strip().title()
        page_size = min(page_size, 20)  # safety limit
        today = datetime.now().strftime("%Y-%m-%d")
        start_date = start_date or today

        # Parse and fix start_date
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
            if start_date_obj.date() < datetime.now().date():
                start_date_obj = datetime.now()
                start_date = start_date_obj.strftime("%Y-%m-%d")
        except:
            start_date = today
            start_date_obj = datetime.now()

        end_date = (start_date_obj + timedelta(days=30)).strftime("%Y-%m-%d")

        # Resolve destination ID (uses cached destinations)
        dest_id = self.resolve_destination(destination_norm)

        # BUILD CACHE KEY
        cache_parts = f"{destination_norm}|{start_date}|{end_date}|{page_size}"
        cache_key = f"viator:tours:{hashlib.md5(cache_parts.encode()).hexdigest()}"

        # TRY CACHE FIRST
        cached = self.api_cache.get(cache_key)
        if cached is not None:
            logger.info(f"[Cache HIT] Viator tours in {destination_norm}")
            return cached

        logger.info(f"[Cache MISS] Calling Viator API for tours in {destination_norm}")

        # API payload
        payload = {
            "filtering": {
                "destination": str(dest_id),
                "startDate": start_date,
                "endDate": end_date,
                "highestPrice": 10000,
                "durationInMinutes": {"from": 0, "to": 1000},
                "rating": {"from": 0, "to": 5}
            },
            "productSorting": {
                "sort": "PRICE", 
                "order": "ASCENDING"
            },
            "searchTypes": [
                {"searchType": "PRODUCTS", "pagination": {"start": 1, "count": page_size}}
            ],
            "currency": "USD"
        }

        data = self._make_request("POST", "products/search", json=payload)
        
        # Parse response
        tours_data = None
        if "data" in data:
            tours_data = data["data"]
        elif isinstance(data, list):
            tours_data = data
        elif "products" in data:
            tours_data = data["products"]
        else:
            result = []
            # Cache empty result for shorter time
            self.api_cache.set(cache_key, result, timeout=60 * 5)
            logger.info(f"[Viator] No tours found for {destination_norm}")
            return result

        result = self._format_tours(tours_data)

        # CACHE FOR 60 MINUTES
        self.api_cache.set(cache_key, result, timeout=self.CACHE_TTL_SEARCH)
        logger.info(f"[Viator] Found {len(result)} tours, cached for {self.CACHE_TTL_SEARCH}s")
        return result

    # ================================================================
    # PRODUCT DETAILS - CACHED
    # ================================================================
    def get_product_details(self, product_code: str) -> Dict:
        """Fetch detailed product information - cached for 30 minutes."""
        cache_key = f"viator:product:{product_code}"
        
        # Try cache first
        cached = self.api_cache.get(cache_key)
        if cached:
            logger.info(f"[Cache HIT] Product details for {product_code}")
            return cached
        
        logger.info(f"[Cache MISS] Fetching product {product_code}")
        
        data = self._make_request("GET", f"products/{product_code}")
        product = data.get("data", data)
        
        formatted = {
            "code": product.get("productCode", ""),
            "title": product.get("title", ""),
            "description": product.get("description", ""),
            "price": float(product.get("pricing", {}).get("summary", {}).get("fromPrice", 0)),
            "duration": product.get("duration", {}).get("durationText", "N/A"),
            "rating": float(product.get("reviews", {}).get("combinedAverageRating", 0)),
            "reviewCount": product.get("reviews", {}).get("totalReviews", 0),
            "url": self._add_affiliate_tracking(product.get("webUrl", "")),
            "images": [img.get("url") for img in product.get("images", [])[:5]],
            "location": product.get("location", {}).get("address", ""),
            "inclusions": product.get("inclusions", []),
            "exclusions": product.get("exclusions", []),
            "cancellationPolicy": product.get("cancellationPolicy", {}).get("description", "")
        }
        
        # Cache for 30 minutes
        self.api_cache.set(cache_key, formatted, timeout=self.CACHE_TTL_PRODUCT_DETAILS)
        logger.info(f"[Viator] Product {product_code} cached")
        return formatted

    # ================================================================
    # AVAILABILITY - SHORT CACHE
    # ================================================================
    def check_availability(self, product_code: str) -> Dict:
        """Check availability for a specific tour - cached for 10 minutes."""
        cache_key = f"viator:avail:{product_code}"
        
        # Try cache first
        cached = self.api_cache.get(cache_key)
        if cached:
            logger.info(f"[Cache HIT] Availability for {product_code}")
            return cached
        
        logger.info(f"[Cache MISS] Checking availability for {product_code}")
        
        data = self._make_request("GET", f"availability/schedules/{product_code}")
        if not data or "schedules" not in data:
            raise ViatorAPIError(404, f"No availability found for product {product_code}.")
        
        result = {"product_code": product_code, "schedules": data["schedules"][:10]}
        
        # Cache for 10 minutes (availability changes more frequently)
        self.api_cache.set(cache_key, result, timeout=self.CACHE_TTL_AVAILABILITY)
        logger.info(f"[Viator] Availability for {product_code} cached")
        return result

    # ================================================================
    # HELPERS
    # ================================================================
    def _format_tours(self, tours: List[Dict]) -> List[Dict]:
        """Format raw tour data into standardized output."""
        formatted = []
        for item in tours:
            images = item.get("images", [])
            thumbnail = images[0].get("url", "") if images else ""
            
            # Get or create URL
            web_url = item.get("webUrl", "")
            if not web_url and item.get("productCode"):
                web_url = f"https://www.viator.com/tours/d{item['productCode']}"
            
            formatted.append({
                "code": item.get("productCode", ""),
                "title": item.get("title", "Untitled"),
                "price": float(item.get("pricing", {}).get("summary", {}).get("fromPrice", 0)),
                "rating": float(item.get("reviews", {}).get("combinedAverageRating", 0)),
                "reviewCount": item.get("reviews", {}).get("totalReviews", 0),
                "duration": item.get("duration", {}).get("durationText", "N/A"),
                "thumbnail": thumbnail,
                "url": self._add_affiliate_tracking(web_url)
            })
        return formatted

    def _add_affiliate_tracking(self, url: str) -> str:
        """Add affiliate tracking parameters to Viator product URLs."""
        if not url or not self.AFFILIATE_ID:
            return url
        return f"{url}{'&' if '?' in url else '?'}pid={self.AFFILIATE_ID}&mcid=42383"

    # ================================================================
    # CACHE MANAGEMENT
    # ================================================================
    @classmethod
    def clear_cache(cls, destination: str = None, product_code: str = None):
        """Clear Viator cache, optionally filtered."""
        api_cache = caches['api_cache']
        
        if product_code:
            keys_to_clear = [
                f"viator:product:{product_code}",
                f"viator:avail:{product_code}"
            ]
            for key in keys_to_clear:
                api_cache.delete(key)
                logger.info(f"[Viator] Cleared cache for {key}")
        
        elif destination:
            # Would need Redis SCAN for pattern matching
            logger.warning(f"[Viator] Destination-specific cache clear requires Redis SCAN")
        
        else:
            logger.warning("[Viator] Full cache clear not recommended")
    
    @classmethod
    def get_cache_stats(cls):
        """Get cache statistics."""
        return {
            'service': 'viator',
            'cache_backend': 'redis',
            'cache_alias': 'api_cache',
            'ttl_search': cls.CACHE_TTL_SEARCH,
            'ttl_destinations': cls.CACHE_TTL_DESTINATIONS,
            'ttl_product_details': cls.CACHE_TTL_PRODUCT_DETAILS,
            'ttl_availability': cls.CACHE_TTL_AVAILABILITY,
        }


# ================================================================
# TEST SCRIPT
# ================================================================
if __name__ == "__main__":
    service = ViatorService()
    logger.info("=== Viator Enhanced Caching Test ===")

    for city in ["Rome", "Paris", "London"]:
        try:
            logger.info(f"\n--- Searching tours in {city} ---")
            tours = service.search_tours("sightseeing", city, page_size=3)
            logger.info(f" Found {len(tours)} tours.")
            for t in tours[:2]:
                logger.info(f"  - {t['title']} (${t['price']}) [{t['rating']}★]")
        except ViatorAPIError as e:
            logger.error(f" Error: {e}")