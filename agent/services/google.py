#Agents/services/google.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

class GooglePlacesAPIError(Exception):
    pass

class GooglePlacesService:
    BASEURL = "https://maps.googleapis.com/maps/api/place"
    API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

    def __init__(self):
        if not self.API_KEY:
            raise ValueError("Google Places API key not found in environment variables.")
        
    

    def search_places(self, query: str, limit: int = 5):
        """Text-based search for places."""
        url = f"{self.BASE_URL}/textsearch/json"
        params = {
            "query": query,
            "key": self.API_KEY
        }

        response = requests.get(url, params=params)
        data = response.json()

        if response.status_code != 200 or "results" not in data:
            raise GooglePlacesAPIError(data.get("error_message", "Unknown error"))

        return [
            {
                "name": p.get("name"),
                "address": p.get("formatted_address"),
                "rating": p.get("rating"),
                "user_ratings_total": p.get("user_ratings_total"),
                "place_id": p.get("place_id"),
                "types": p.get("types", []),
                "photo_ref": p.get("photos", [{}])[0].get("photo_reference", None),
                "location": p.get("geometry", {}).get("location", {}),
            }
            for p in data["results"][:limit]
        ]

    def get_place_details(self, place_id: str):
        """Get detailed info for a place by its place_id."""
        url = f"{self.BASE_URL}/details/json"
        params = {
            "place_id": place_id,
            "key": self.API_KEY,
            "fields": "name,formatted_address,geometry,website,formatted_phone_number,rating,review,photo,url"
        }

        response = requests.get(url, params=params)
        data = response.json()

        if response.status_code != 200 or "result" not in data:
            raise GooglePlacesAPIError(data.get("error_message", "Unknown error"))

        return data["result"]

    def get_photo_url(self, photo_ref: str, max_width: int = 800):
        """Generate a photo URL from a photo reference."""
        return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={max_width}&photo_reference={photo_ref}&key={self.API_KEY}"