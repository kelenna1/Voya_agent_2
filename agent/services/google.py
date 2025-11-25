# agent/services/google_places.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()


class GooglePlacesAPIError(Exception):
    """Custom exception for Google Places API errors."""
    pass


class GooglePlacesService:
    BASE_URL = "https://places.googleapis.com/v1"
    API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
   
    def __init__(self):
        if not self.API_KEY:
            raise ValueError("Missing GOOGLE_PLACES_API_KEY in environment variables.")
        self.headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.API_KEY,
            "X-Goog-FieldMask": "*"
        }

    def search_places(self, query: str, limit: int = 5):
        """
        Text-based search for places using the latest Google Places API (v1).
        Example query: 'restaurants in Rome' or 'hotels near Eiffel Tower'
        
        Returns:
            List of formatted place dictionaries
        """
        url = f"{self.BASE_URL}/places:searchText"
        payload = {
            "textQuery": query,
            "pageSize": limit
        }
        
        response = requests.post(url, headers=self.headers, json=payload, timeout=30)
        data = response.json()
        
        if response.status_code != 200:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            raise GooglePlacesAPIError(f"API error {response.status_code}: {error_msg}")
        
        if "places" not in data:
            # Return empty list instead of raising error for no results
            return []
        
        results = []
        for place in data["places"]:
            location = place.get("location", {})
            photos = place.get("photos", [])
            
            # Get the first photo reference if available
            photo_ref = None
            photo_url = None
            if photos and len(photos) > 0:
                photo_name = photos[0].get("name", "")
                if photo_name:
                    photo_ref = photo_name.split("/")[-1]
                    photo_url = self.get_photo_url(photo_name)
            
            results.append({
                "name": place.get("displayName", {}).get("text", "Unknown"),
                "address": place.get("formattedAddress", "Address not available"),
                "rating": place.get("rating", 0),
                "user_ratings_total": place.get("userRatingCount", 0),
                "place_id": place.get("id", ""),
                "types": place.get("types", []),
                "photo_ref": photo_ref,
                "photo_url": photo_url,
                "location": {
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                },
            })
        
        return results

    def get_place_details(self, place_id: str):
        """
        Fetch detailed info for a specific place by its ID.
        Uses: GET /v1/places/{placeId}
        
        Returns:
            Dictionary with place details
        """
        url = f"{self.BASE_URL}/places/{place_id}"
        
        response = requests.get(url, headers=self.headers, timeout=30)
        data = response.json()
        
        if response.status_code != 200:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            raise GooglePlacesAPIError(f"API error {response.status_code}: {error_msg}")
        
        if "id" not in data:
            raise GooglePlacesAPIError(f"Place not found: {place_id}")
        
        # Format the response consistently
        location = data.get("location", {})
        photos = data.get("photos", [])
        
        return {
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
            "opening_hours": data.get("regularOpeningHours", {})
        }

    def get_photo_url(self, photo_name: str, max_width: int = 800):
        """
        Generate a direct photo URL from the photo resource name.
        
        Args:
            photo_name: Full photo name (e.g. 'places/XYZ/photos/ABC')
            max_width: Maximum width in pixels
            
        Returns:
            Direct URL to the photo or None
        """
        if not photo_name:
            return None
        
        return f"https://places.googleapis.com/v1/{photo_name}/media?maxWidthPx={max_width}&key={self.API_KEY}"


# # Test script
# if __name__ == "__main__":
#     service = GooglePlacesService()
#     print("=== Google Places API Test ===\n")
    
#     try:
#         print("Searching for 'restaurants in Rome'...")
#         places = service.search_places("restaurants in Rome", limit=3)
#         print(f"Found {len(places)} places:\n")
        
#         for place in places:
#             print(f"- {place['name']}")
#             print(f"  Rating: {place['rating']} ({place['user_ratings_total']} reviews)")
#             print(f"  Address: {place['address']}")
#             if place.get('photo_url'):
#                 print(f"  Photo: {place['photo_url']}")
#             print()
            
#     except GooglePlacesAPIError as e:
#         print(f"[Error] {e}")