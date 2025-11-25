# agent/services/mistifly.py - ASR Hub API Complete
import os
import requests
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from django.core.cache import cache

load_dotenv()

class MistiflyAPIError(Exception):
    def __init__(self, status_code: int = 0, message: str = ""):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Mistifly API error {status_code}: {message}")

class MistiflyService:
    BASE_URL = os.getenv("MISTIFLY_BASE_URL", "https://restapidemo.myfarebox.com").rstrip('/')
    USERNAME = os.getenv("MISTIFLY_USERNAME")
    PASSWORD = os.getenv("MISTIFLY_PASSWORD")
    ACCOUNT_NUMBER = os.getenv("MISTIFLY_ACCOUNT_NUMBER")
    
    SESSION_CACHE_KEY = "mistifly_auth_token"
    SESSION_TIMEOUT = 3600 * 23  # 23 hours
    
    MAX_FLIGHTS_RETURN = 10

    def __init__(self):
        if not all([self.USERNAME, self.PASSWORD, self.ACCOUNT_NUMBER]):
            raise ValueError("Missing credentials. Please set MISTIFLY variables in .env")

    # ================================================================
    # AUTHENTICATION (ASR Hub - Bearer Token)
    # ================================================================
    def _create_session(self) -> str:
        """Create ASR Hub session and get Bearer token."""
        url = f"{self.BASE_URL}/api/CreateSession"
        payload = {
            "UserName": self.USERNAME,
            "Password": self.PASSWORD,
            "AccountNumber": self.ACCOUNT_NUMBER
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            try:
                data = response.json()
            except ValueError:
                raise MistiflyAPIError(response.status_code, f"Invalid JSON: {response.text[:200]}")

            session_id = None
            if "Data" in data and isinstance(data["Data"], dict):
                session_id = data["Data"].get("SessionId")
            else:
                session_id = data.get("SessionId")
            
            if not session_id:
                msg = data.get("Message") or str(data)
                raise MistiflyAPIError(500, f"No SessionId found. Response: {msg}")

            cache.set(self.SESSION_CACHE_KEY, session_id, timeout=self.SESSION_TIMEOUT)
            print(f"[Mistifly ASR] Created session: {session_id[:8]}...")
            return session_id
        except requests.exceptions.RequestException as e:
            raise MistiflyAPIError(0, f"Network error during auth: {str(e)}")

    def _get_token(self) -> str:
        """Get valid Bearer token, refresh if expired."""
        token = cache.get(self.SESSION_CACHE_KEY)
        if token: 
            return token
        return self._create_session()

    def _post_authenticated(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make authenticated POST request with Bearer token."""
        token = self._get_token()
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}", 
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=45)
            
            # Handle 401 - token expired, refresh and retry
            if response.status_code == 401:
                cache.delete(self.SESSION_CACHE_KEY)
                token = self._create_session()
                headers["Authorization"] = f"Bearer {token}"
                response = requests.post(url, json=payload, headers=headers, timeout=45)

            data = response.json()
            
            if not response.ok:
                error_msg = data.get("Message") or str(data)
                raise MistiflyAPIError(response.status_code, error_msg)
            
            return data
            
        except requests.exceptions.RequestException as e:
            raise MistiflyAPIError(0, f"Network error: {str(e)}")

    # ================================================================
    # FLIGHT SEARCH
    # ================================================================
    def search_flights(
        self, 
        origin, 
        destination, 
        departure_date, 
        return_date=None, 
        adults=1, 
        children=0, 
        infants=0, 
        cabin_class="Y", 
        limit=5
    ):
        """Search flights using ASR Hub API."""
        cabin_map = {"ECONOMY": "Y", "BUSINESS": "C", "FIRST": "F", "PREMIUM_ECONOMY": "S"}
        cabin_code = cabin_map.get(cabin_class.upper(), cabin_class)

        payload = {
            "OriginDestinationInformations": [{
                "DepartureDateTime": f"{departure_date}T00:00:00",
                "OriginLocationCode": origin.upper(),
                "DestinationLocationCode": destination.upper()
            }],
            "TravelPreferences": {
                "MaxStopsQuantity": "All",
                "CabinPreference": cabin_code,
                "Preferences": {
                    "CabinClassPreference": {
                        "CabinType": cabin_code, 
                        "PreferenceLevel": "Preferred"
                    }
                },
                "AirTripType": "OneWay"
            },
            "PricingSourceType": "All",
            "PassengerTypeQuantities": [{"Code": "ADT", "Quantity": adults}],
            "RequestOptions": "Fifty",
            "Target": "Test"
        }

        if return_date:
            payload["TravelPreferences"]["AirTripType"] = "Return"
            payload["OriginDestinationInformations"].append({
                "DepartureDateTime": f"{return_date}T00:00:00",
                "OriginLocationCode": destination.upper(),
                "DestinationLocationCode": origin.upper()
            })

        try:
            data = self._post_authenticated("api/v1/Search/Flight", payload)
            
            search_data = data
            if "Data" in data and isinstance(data["Data"], dict):
                search_data = data["Data"]
            
            itineraries = search_data.get("PricedItineraries", [])
            if not itineraries: 
                return []

            # Sort by price and limit
            safe_limit = min(limit, self.MAX_FLIGHTS_RETURN)
            
            def get_price(itin):
                try:
                    return float(itin.get("AirItineraryPricingInfo", {})
                        .get("ItinTotalFare", {})
                        .get("TotalFare", {})
                        .get("Amount", 999999))
                except: 
                    return 999999
            
            itineraries.sort(key=get_price)
            limited_itineraries = itineraries[:safe_limit]

            return self._format_flights(limited_itineraries, include_raw=False)

        except Exception as e:
            raise MistiflyAPIError(0, f"Search Error: {str(e)}")

    # ================================================================
    # RE-FETCH FOR BOOKING
    # ================================================================
    def get_full_itinerary_for_booking(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        flight_index: int,
        return_date: str = None,
        adults: int = 1,
        cabin_class: str = "ECONOMY"
    ) -> Dict:
        """Re-fetch search with raw_itinerary for booking."""
        cabin_map = {"ECONOMY": "Y", "BUSINESS": "C", "FIRST": "F", "PREMIUM_ECONOMY": "S"}
        cabin_code = cabin_map.get(cabin_class.upper(), cabin_class)

        payload = {
            "OriginDestinationInformations": [{
                "DepartureDateTime": f"{departure_date}T00:00:00",
                "OriginLocationCode": origin.upper(),
                "DestinationLocationCode": destination.upper()
            }],
            "TravelPreferences": {
                "MaxStopsQuantity": "All",
                "CabinPreference": cabin_code,
                "Preferences": {
                    "CabinClassPreference": {
                        "CabinType": cabin_code,
                        "PreferenceLevel": "Preferred"
                    }
                },
                "AirTripType": "OneWay"
            },
            "PricingSourceType": "All",
            "PassengerTypeQuantities": [{"Code": "ADT", "Quantity": adults}],
            "RequestOptions": "Fifty",
            "Target": "Test"
        }

        if return_date:
            payload["TravelPreferences"]["AirTripType"] = "Return"
            payload["OriginDestinationInformations"].append({
                "DepartureDateTime": f"{return_date}T00:00:00",
                "OriginLocationCode": destination.upper(),
                "DestinationLocationCode": origin.upper()
            })

        try:
            data = self._post_authenticated("api/v1/Search/Flight", payload)
            
            search_data = data
            if "Data" in data and isinstance(data["Data"], dict):
                search_data = data["Data"]
            
            itineraries = search_data.get("PricedItineraries", [])
            if not itineraries or flight_index >= len(itineraries):
                raise MistiflyAPIError(404, f"Flight {flight_index} not found")

            # Sort by price to match original search
            def get_price(itin):
                try:
                    return float(itin.get("AirItineraryPricingInfo", {})
                        .get("ItinTotalFare", {})
                        .get("TotalFare", {})
                        .get("Amount", 999999))
                except:
                    return 999999
            
            itineraries.sort(key=get_price)
            
            # Return with raw_itinerary
            selected_itin = itineraries[flight_index]
            formatted = self._format_flights([selected_itin], include_raw=True)
            
            if formatted:
                return formatted[0]
            else:
                raise MistiflyAPIError(404, "Could not format selected flight")
                
        except Exception as e:
            raise MistiflyAPIError(0, f"Re-fetch error: {str(e)}")

    # ================================================================
    # PRICE CHECK
    # ================================================================
    def check_price(self, flight_id: str, raw_itinerary: Dict) -> Dict:
        """Revalidate flight price before booking (ASR Hub)."""
        try:
            payload = {"PricedItinerary": raw_itinerary}
            data = self._post_authenticated("api/v1/Price/Flight", payload)
            
            price_data = data.get("Data", data)
            priced_itin = price_data.get("PricedItinerary", {})
            pricing_info = priced_itin.get("AirItineraryPricingInfo", {})
            total_fare = pricing_info.get("ItinTotalFare", {}).get("TotalFare", {})
            
            return {
                "itinerary_id": flight_id,
                "total_fare": float(total_fare.get("Amount", 0)),
                "currency": total_fare.get("CurrencyCode", "USD"),
                "is_price_changed": data.get("IsPriceChanged", False),
                "is_available": not data.get("IsPriceChanged", False)
            }
        except Exception as e:
            raise MistiflyAPIError(0, f"Price check error: {str(e)}")

    # ================================================================
    # BOOKING
    # ================================================================
    def book_flight(
        self,
        itinerary: Dict,
        passengers: List[Dict],
        contact_email: str,
        contact_phone: str
    ) -> Dict:
        """Book flight with passenger details (ASR Hub)."""
        try:
            # Format passengers for ASR Hub API
            formatted_passengers = []
            for idx, pax in enumerate(passengers):
                name_parts = pax.get("name", "").split(" ", 1)
                first_name = name_parts[0] if len(name_parts) > 0 else "Unknown"
                last_name = name_parts[1] if len(name_parts) > 1 else "Traveler"
                
                formatted_passengers.append({
                    "PassengerType": "ADT",
                    "Gender": pax.get("gender", "M"),
                    "PassengerName": {
                        "PassengerTitle": pax.get("title", "Mr" if pax.get("gender") == "M" else "Ms"),
                        "PassengerFirstName": first_name,
                        "PassengerLastName": last_name
                    },
                    "DateOfBirth": pax.get("dob", "1990-01-01"),
                    "Passport": {
                        "PassportNumber": pax.get("passport", ""),
                        "Country": pax.get("passport_country", "NG"),
                        "ExpiryDate": pax.get("passport_expiry", "2030-01-01")
                    },
                    "PassengerNationality": pax.get("nationality", "NG"),
                    "NationalID": pax.get("national_id", "")
                })
            
            # Get raw itinerary
            raw_itin = itinerary.get("raw_itinerary")
            if not raw_itin:
                raise ValueError("Cannot book: raw_itinerary not found. Please re-fetch flight data.")
            
            payload = {
                "PricedItinerary": raw_itin,
                "Passengers": formatted_passengers,
                "ContactInfo": {
                    "Email": contact_email,
                    "Phone": contact_phone
                }
            }
            
            data = self._post_authenticated("api/v1/Book/Flight", payload)
            
            booking_data = data.get("Data", data)
            
            return {
                "order_id": booking_data.get("OrderId") or booking_data.get("BookingId"),
                "pnr": booking_data.get("PNR"),
                "booking_reference": booking_data.get("BookingReferenceID"),
                "status": booking_data.get("Status", "CONFIRMED"),
                "total_amount": booking_data.get("TotalAmount", 0),
                "currency": booking_data.get("Currency", "USD"),
                "message": "Booking successful. Proceed with payment to issue ticket."
            }
            
        except Exception as e:
            raise MistiflyAPIError(0, f"Booking error: {str(e)}")

    # ================================================================
    # TICKETING
    # ================================================================
    def issue_ticket(self, order_id: str) -> Dict:
        """Issue e-ticket after payment (ASR Hub)."""
        try:
            payload = {"OrderId": order_id}
            data = self._post_authenticated("api/v1/Ticket/Issue", payload)
            
            ticket_data = data.get("Data", data)
            
            return {
                "order_id": order_id,
                "ticket_numbers": ticket_data.get("TicketNumbers", []),
                "pnr": ticket_data.get("PNR"),
                "status": ticket_data.get("Status", "TICKETED"),
                "airline_pnr": ticket_data.get("AirlinePNR"),
                "message": "E-ticket issued successfully"
            }
            
        except Exception as e:
            raise MistiflyAPIError(0, f"Ticketing error: {str(e)}")

    # ================================================================
    # RETRIEVE BOOKING
    # ================================================================
    def get_booking_details(self, order_id: str) -> Dict:
        """Retrieve booking details by OrderID (ASR Hub)."""
        try:
            payload = {"OrderId": order_id}
            data = self._post_authenticated("api/v1/Booking/Details", payload)
            return data.get("Data", data)
            
        except Exception as e:
            raise MistiflyAPIError(0, f"Retrieve booking error: {str(e)}")

    # ================================================================
    # FORMATTING HELPERS
    # ================================================================
    def _format_flights(self, itineraries: List[Dict], include_raw=False) -> List[Dict]:
        """Format flight data for frontend."""
        formatted = []
        for idx, itin in enumerate(itineraries):
            try:
                pricing_info = itin.get("AirItineraryPricingInfo", {})
                total_fare = pricing_info.get("ItinTotalFare", {}).get("TotalFare", {})
                od_options = itin.get("OriginDestinationOptions", [])
                
                if not od_options: 
                    continue
                    
                first_leg = od_options[0].get("FlightSegments", [])
                if not first_leg: 
                    continue
                
                first_seg = first_leg[0]
                last_seg = first_leg[-1]
                
                duration = sum(int(opt.get("JourneyDuration", 0)) for opt in od_options)
                stops = sum(max(0, len(opt.get("FlightSegments", [])) - 1) for opt in od_options)

                flight_obj = {
                    "id": f"flight_{idx}",
                    "airline": first_seg.get("OperatingAirline", {}).get("Code", "XX"),
                    "flight_number": first_seg.get("FlightNumber", ""),
                    "origin": first_seg.get("DepartureAirportLocationCode"),
                    "destination": last_seg.get("ArrivalAirportLocationCode"),
                    "departure_time": first_seg.get("DepartureDateTime"),
                    "arrival_time": last_seg.get("ArrivalDateTime"),
                    "duration_text": f"{duration//60}h {duration%60}m",
                    "stops": stops,
                    "price": float(total_fare.get("Amount", 0)),
                    "currency": total_fare.get("CurrencyCode", "USD"),
                    "segments": self._format_segments(od_options),
                }

                if include_raw:
                    flight_obj["raw_itinerary"] = itin
                else:
                    flight_obj["booking_key"] = {
                        "sequence": itin.get("SequenceNumber"),
                        "provider": itin.get("Provider"),
                        "validating_airline": itin.get("ValidatingAirlineCode")
                    }

                formatted.append(flight_obj)
            except Exception:
                continue
        return formatted

    def _format_segments(self, od_options):
        """Format flight segments."""
        segs = []
        for leg in od_options:
            for s in leg.get("FlightSegments", []):
                segs.append({
                    "airline": s.get("OperatingAirline", {}).get("Code"),
                    "flight": s.get("FlightNumber"),
                    "origin": s.get("DepartureAirportLocationCode"),
                    "dest": s.get("ArrivalAirportLocationCode"),
                    "dep": s.get("DepartureDateTime"),
                    "arr": s.get("ArrivalDateTime")
                })
        return segs