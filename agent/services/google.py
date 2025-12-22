# agent/services/google.py - ENHANCED CACHING VERSION
import os
import requests
from dotenv import load_dotenv
from django.core.cache import cache, caches
import hashlib
import logging

load_dotenv()
logger = logging.getLogger(__name__)


class GooglePlacesAPIError(Exception):
    """Custom exception for Google Places API errors."""
    pass


class GooglePlacesService:
    BASE_URL = "https://places.googleapis.com/v1"
    API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
    
    # Cache configuration
    CACHE_TTL_SEARCH = 60 * 30  # 30 minutes (places don't change often)
    CACHE_TTL_DETAILS = 60 * 60  # 60 minutes (details change even less)
    CACHE_TTL_PHOTO = 60 * 60 * 24  # 24 hours (photos rarely change)

    def __init__(self):
        if not self.API_KEY:
            raise ValueError("Missing GOOGLE_PLACES_API_KEY in environment variables.")
        
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.API_KEY,
            "X-Goog-FieldMask": "*"
        }
        
        # Use api_cache for faster responses
        self.api_cache = caches['api_cache']

    # ================================================================
    # TEXT SEARCH - CACHED
    # ================================================================
    def search_places(self, query: str, limit: int = 5):
        """Search for places - cached for 30 minutes."""
        # Normalize query for cache key
        query_norm = query.strip().lower()
        cache_key = f"places:search:{hashlib.md5(f'{query_norm}|{limit}'.encode()).hexdigest()}"

        # Try cache first
        cached = self.api_cache.get(cache_key)
        if cached:
            logger.info(f"[Cache HIT] Google Places search: '{query}'")
            return cached

        logger.info(f"[Cache MISS] Calling Google Places API for '{query}'")

        url = f"{self.BASE_URL}/places:searchText"
        payload = {
            "textQuery": query,
            "pageSize": limit
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            data = response.json()

            if response.status_code != 200:
                error_msg = data.get("error", {}).get("message", "Unknown error")
                logger.error(f"[Google Places] API error {response.status_code}: {error_msg}")
                raise GooglePlacesAPIError(f"API error {response.status_code}: {error_msg}")

            if "places" not in data:
                # Cache empty result for shorter time
                self.api_cache.set(cache_key, [], timeout=60 * 5)
                logger.info(f"[Google Places] No places found for '{query}'")
                return []

            # Format results
            results = []
            for place in data["places"]:
                location = place.get("location", {})
                photos = place.get("photos", [])
                photo_url = None
                
                if photos:
                    photo_name = photos[0].get("name", "")
                    if photo_name:
                        photo_url = self.get_photo_url(photo_name)

                results.append({
                    "name": place.get("displayName", {}).get("text", "Unknown"),
                    "address": place.get("formattedAddress", "Address not available"),
                    "rating": place.get("rating", 0),
                    "user_ratings_total": place.get("userRatingCount", 0),
                    "place_id": place.get("id"),
                    "types": place.get("types", []),
                    "photo_url": photo_url,
                    "location": {
                        "latitude": location.get("latitude"),
                        "longitude": location.get("longitude"),
                    },
                })

            # Cache for 30 minutes
            self.api_cache.set(cache_key, results, timeout=self.CACHE_TTL_SEARCH)
            logger.info(f"[Google Places] Found {len(results)} places for '{query}', cached")
            return results

        except requests.exceptions.RequestException as e:
            logger.error(f"[Google Places] Request failed: {e}")
            raise GooglePlacesAPIError(f"Request failed: {str(e)}")

    # ================================================================
    # PLACE DETAILS - CACHED
    # ================================================================
    def get_place_details(self, place_id: str):
        """Get detailed place information - cached for 60 minutes."""
        cache_key = f"places:details:{place_id}"

        # Try cache first
        cached = self.api_cache.get(cache_key)
        if cached:
            logger.info(f"[Cache HIT] Place details for {place_id}")
            return cached

        logger.info(f"[Cache MISS] Fetching place details for {place_id}")

        url = f"{self.BASE_URL}/places/{place_id}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            data = response.json()

            if response.status_code != 200:
                error_msg = data.get("error", {}).get("message", "Unknown error")
                logger.error(f"[Google Places] Details API error {response.status_code}: {error_msg}")
                raise GooglePlacesAPIError(f"API error {response.status_code}: {error_msg}")

            if "id" not in data:
                raise GooglePlacesAPIError(f"Place not found: {place_id}")

            # Format response
            photos = data.get("photos", [])
            location = data.get("location", {})

            formatted = {
                "place_id": data.get("id", ""),
                "name": data.get("displayName", {}).get("text", "Unknown"),
                "address": data.get("formattedAddress", ""),
                "website": data.get("websiteUri", ""),
                "phone": data.get("internationalPhoneNumber", ""),
                "rating": data.get("rating", 0),
                "user_ratings_total": data.get("userRatingCount", 0),
                "location": {
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                },
                "photos": [self.get_photo_url(p.get("name", "")) for p in photos[:5]],
                "opening_hours": data.get("regularOpeningHours", {}),
            }

            # Cache for 60 minutes
            self.api_cache.set(cache_key, formatted, timeout=self.CACHE_TTL_DETAILS)
            logger.info(f"[Google Places] Details for {place_id} cached")
            return formatted

        except requests.exceptions.RequestException as e:
            logger.error(f"[Google Places] Request failed: {e}")
            raise GooglePlacesAPIError(f"Request failed: {str(e)}")

    # ================================================================
    # PHOTO URL - CACHED
    # ================================================================
    def get_photo_url(self, photo_name: str, max_width: int = 800):
        """Generate photo URL - cached for 24 hours."""
        if not photo_name:
            return None
        
        # Cache key includes photo name and size
        cache_key = f"places:photo:{hashlib.md5(f'{photo_name}|{max_width}'.encode()).hexdigest()}"
        
        # Try cache first
        cached_url = self.api_cache.get(cache_key)
        if cached_url:
            logger.debug(f"[Cache HIT] Photo URL for {photo_name[:20]}...")
            return cached_url
        
        # Generate URL
        photo_url = (
            f"https://places.googleapis.com/v1/{photo_name}/media"
            f"?maxWidthPx={max_width}&key={self.API_KEY}"
        )
        
        # Cache for 24 hours (photos rarely change)
        self.api_cache.set(cache_key, photo_url, timeout=self.CACHE_TTL_PHOTO)
        return photo_url

    # ================================================================
    # CACHE MANAGEMENT
    # ================================================================
    @classmethod
    def clear_cache(cls, place_id: str = None):
        """Clear Google Places cache."""
        api_cache = caches['api_cache']
        
        if place_id:
            keys_to_clear = [
                f"places:details:{place_id}"
            ]
            for key in keys_to_clear:
                api_cache.delete(key)
                logger.info(f"[Google Places] Cleared cache for {key}")
        else:
            logger.warning("[Google Places] Full cache clear not recommended")
    
    @classmethod
    def get_cache_stats(cls):
        """Get cache statistics."""
        return {
            'service': 'google_places',
            'cache_backend': 'redis',
            'cache_alias': 'api_cache',
            'ttl_search': cls.CACHE_TTL_SEARCH,
            'ttl_details': cls.CACHE_TTL_DETAILS,
            'ttl_photo': cls.CACHE_TTL_PHOTO,
        }


# ================================================================
# TEST SCRIPT
# ================================================================
if __name__ == "__main__":
    service = GooglePlacesService()
    logger.info("=== Google Places Enhanced Caching Test ===")

    queries = ["hotels in Rome", "restaurants in Paris", "museums in London"]
    
    for query in queries:
        try:
            logger.info(f"\n--- Searching: {query} ---")
            places = service.search_places(query, limit=3)
            logger.info(f"Found {len(places)} places")
            for p in places[:2]:
                logger.info(f"  - {p['name']} ({p['rating']}★)")
        except GooglePlacesAPIError as e:
            logger.error(f"Error: {e}")