# agent/services/viator.py
import os
import requests
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import List, Dict, Optional
from functools import wraps
import json

load_dotenv()


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
                        print(f"[Rate Limit] Retrying in {wait_time}s...")
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

    def __init__(self):
        if not self.HEADERS["exp-api-key"]:
            raise ValueError("Missing VIATOR_API_KEY in environment variables. Please set VIATOR_API_KEY in your .env file.")
        self.destinations_cache = None

    # ------------------------------------------------------------------
    # API REQUEST WRAPPER
    # ------------------------------------------------------------------
    @retry_on_rate_limit()
    def _make_request(self, method: str, endpoint: str,
                      params: Dict = None, json: Dict = None) -> Optional[Dict]:
        """Make a Viator API request with error handling and retries."""
        url = f"{self.BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        try:
            response = requests.request(
                method, url,
                headers=self.HEADERS,
                params=params,
                json=json,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            raise ViatorAPIError(408, f"Request timeout for endpoint '{endpoint}'")
        except requests.exceptions.RequestException as e:
            status = e.response.status_code if e.response else 0
            message = e.response.text if e.response else str(e)
            # print(f"DEBUG: Request failed - URL: {url}, Status: {status}, Message: {message}")
            raise ViatorAPIError(status, message)

    # ------------------------------------------------------------------
    # DESTINATIONS
    # ------------------------------------------------------------------
    def get_destinations(self) -> List[Dict]:
        """Fetch destinations (GET /destinations). Cache for efficiency."""
        if self.destinations_cache is None:
            response = self._make_request("GET", "destinations")

            if not response:
                raise ViatorAPIError(500, "Empty response from Viator /destinations endpoint.")

            # DEBUG: print the top-level keys once (uncomment for debugging)
            # print(f"DEBUG: /destinations response keys -> {list(response.keys())}")

            # Handle the different possible response structures
            if isinstance(response, list):
                # Some versions return a direct list
                self.destinations_cache = response

            elif isinstance(response, dict):
                # Case 1: Viator production often returns {"destinations": [...]}
                if "destinations" in response:
                    self.destinations_cache = response["destinations"]

                # Case 2: Some versions wrap in {"data": {"destinations": [...]}}
                elif "data" in response and isinstance(response["data"], dict) and "destinations" in response["data"]:
                    self.destinations_cache = response["data"]["destinations"]

                # Case 3: Some versions return {"data": [...]}
                elif "data" in response and isinstance(response["data"], list):
                    self.destinations_cache = response["data"]

                else:
                    raise ViatorAPIError(500, f"Unexpected /destinations format: {response}")
            else:
                raise ViatorAPIError(500, "Unexpected destination response type.")

        return self.destinations_cache



    def resolve_destination(self, name: str) -> str:
        """Resolve destination name to its Viator ID (strict match only)."""
        destinations = self.get_destinations()
        name_lower = name.lower()

        match = next((d for d in destinations if d.get("name", "").lower() == name_lower), None)
        if not match:
            match = next((d for d in destinations if name_lower in d.get("name", "").lower()), None)

        if not match:
            raise ViatorAPIError(404, f"Destination '{name}' not found in Viator database.")
        return int(match.get("destinationId"))

    # ------------------------------------------------------------------
    # TOUR SEARCH
    # ------------------------------------------------------------------
    def search_tours(self, query: Optional[str], destination: str,
                     start_date: Optional[str] = None, page_size: int = 5) -> List[Dict]:
        """Search for tours by query and destination."""
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        # Calculate end_date from start_date (not from now!)
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = (start_date_obj + timedelta(days=30)).strftime("%Y-%m-%d")

        dest_id = self.resolve_destination(destination)

        endpoint = "products/search"

        
        payload = {
            "searchTerm": query or "",        
            "destId": dest_id,           
            "startDate": start_date,
            "endDate": end_date,
            "topX": f"1-{page_size}",     
            "currency": "USD"
        }
        

        # print(f"DEBUG: Making request to {endpoint} with payload: {payload}")
        print(f"\n{'='*60}")
        print(f"DEBUG: Destination '{destination}' resolved to ID: {dest_id} (type: {type(dest_id)})")
        print(f"DEBUG: Start date: {start_date}")
        print(f"DEBUG: End date: {end_date}")
        print(f"DEBUG: Full payload being sent to Viator:")
        print(json.dumps(payload, indent=2))
        print(f"{'='*60}\n")

        data = self._make_request("POST", endpoint, json=payload)
        
        if not data:
            raise ViatorAPIError(404, f"No response received for search in {destination}.")
        
        # Handle different response structures
        tours_data = None
        if "data" in data:
            tours_data = data["data"]
        elif isinstance(data, list):
            tours_data = data
        elif "products" in data:
            tours_data = data["products"]
        else:
            # print(f"DEBUG: Unexpected response structure: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            raise ViatorAPIError(404, f"No tours found for '{query}' in {destination}. Response: {data}")
        
        if not tours_data:
            raise ViatorAPIError(404, f"No tours found for '{query}' in {destination}.")
        
        return self._format_tours(tours_data)

    # ------------------------------------------------------------------
    # PRODUCT DETAILS
    # ------------------------------------------------------------------
    def get_product_details(self, product_code: str) -> Dict:
        """Fetch detailed product information."""
        data = self._make_request("GET", f"products/{product_code}")
        product = data.get("data", data)
        return {
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

    # ------------------------------------------------------------------
    # AVAILABILITY
    # ------------------------------------------------------------------
    def check_availability(self, product_code: str) -> Dict:
        """Check availability for a specific tour."""
        data = self._make_request("GET", f"availability/schedules/{product_code}")
        if not data or "schedules" not in data:
            raise ViatorAPIError(404, f"No availability found for product {product_code}.")
        return {"product_code": product_code, "schedules": data["schedules"][:10]}

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    def _format_tours(self, tours: List[Dict]) -> List[Dict]:
        """Format raw tour data into standardized output."""
        formatted = []
        for item in tours:
            images = item.get("images", [])
            thumbnail = images[0].get("url", "") if images else ""
            formatted.append({
                "code": item.get("productCode", ""),
                "title": item.get("title", "Untitled"),
                "price": float(item.get("pricing", {}).get("summary", {}).get("fromPrice", 0)),
                "rating": float(item.get("reviews", {}).get("combinedAverageRating", 0)),
                "reviewCount": item.get("reviews", {}).get("totalReviews", 0),
                "duration": item.get("duration", {}).get("durationText", "N/A"),
                "thumbnail": thumbnail,
                "url": self._add_affiliate_tracking(item.get("webUrl", ""))
            })
        return formatted

    def _add_affiliate_tracking(self, url: str) -> str:
        """Add affiliate tracking parameters to Viator product URLs."""
        if not url or not self.AFFILIATE_ID:
            return url
        return f"{url}{'&' if '?' in url else '?'}pid={self.AFFILIATE_ID}&mcid=42383"


# ------------------------------------------------------------------
# TEST SCRIPT
# ------------------------------------------------------------------
if __name__ == "__main__":
    service = ViatorService()
    print("=== Viator Production Test ===")

    for city in ["Rome", "Paris", "London"]:
        try:
            print(f"\nSearching tours in {city}...")
            tours = service.search_tours("sightseeing", city, page_size=3)
            print(f"Found {len(tours)} tours.")
            for t in tours[:2]:
                print(f"- {t['title']} (${t['price']}) [{t['rating']}*]")
        except ViatorAPIError as e:
            print(f"[Error] {e}")
