# agent/agent.py - FIXED VERSION
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory
import os
import json
from dotenv import load_dotenv
from agent.services.viator import ViatorService
from agent.services.google import GooglePlacesService
from agent.services.mistifly import MistiflyService
from agent.services.memory import DjangoConversationMemory
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Initialize services
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))
viator = ViatorService()
places = GooglePlacesService()
mistifly = MistiflyService()

# ================================================================
# VIATOR TOOLS (Tours & Activities)
# ================================================================

@tool
def search_viator_tours(query: str = "tour", destination: str = "Rome", date: str = None, limit: int = 5):
    """Search for tours based on query, destination, and date."""
    try:
        if not date:
            date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        tours = viator.search_tours(query, destination, date, limit)
        
        if not tours:
            result = {
                "success": False,
                "message": f"No tours found for '{query}' in {destination} starting {date}.",
                "tours": [],
                "destination": {"name": destination}
            }
            return f"TOUR_SEARCH_RESULT: {json.dumps(result)}"
        
        formatted_tours = []
        for tour in tours:
            tour_url = tour.get("url", "")
            if not tour_url and tour.get("code"):
                tour_url = f"https://www.viator.com/tours/d{tour['code']}"
            
            formatted_tours.append({
                "code": tour.get("code", ""),
                "title": tour.get("title", ""),
                "price": float(tour.get("price", 0)),
                "rating": float(tour.get("rating", 0)),
                "duration": tour.get("duration", "N/A"),
                "url": tour_url,
                "thumbnail": tour.get("thumbnail", "")
            })
        
        result = {
            "success": True,
            "message": f"Found {len(formatted_tours)} tours for '{query}' in {destination}.",
            "tours": formatted_tours,
            "destination": {"name": destination}
        }
        return f"TOUR_SEARCH_RESULT: {json.dumps(result)}"
    except Exception as e:
        result = {
            "success": False,
            "message": f"Error searching tours: {str(e)}",
            "tours": [],
            "destination": {"name": destination}
        }
        return f"TOUR_SEARCH_RESULT: {json.dumps(result)}"


@tool
def check_viator_availability(product_code: str):
    """Check availability schedules for a specific tour product."""
    try:
        schedules = viator.check_availability(product_code)
        return {
            "success": True,
            "message": f"Found {len(schedules)} available schedules",
            "schedules": schedules
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error checking availability: {str(e)}",
            "schedules": []
        }


@tool
def get_destination_info(destination_name: str):
    """Get the Viator destination ID for a given city."""
    try:
        dest_id = viator.resolve_destination(destination_name)
        return {
            "success": True,
            "message": f"Found destination {destination_name}",
            "destination_id": dest_id,
            "destination_name": destination_name
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error resolving destination: {str(e)}"
        }


# ================================================================
# GOOGLE PLACES TOOLS (Hotels, Restaurants, Landmarks)
# ================================================================

@tool
def search_places(query: str, limit: int = 5):
    """Search for places using Google Places API."""
    try:
        results = places.search_places(query, limit)
        
        if not results:
            result = {
                "success": False,
                "message": f"No places found for '{query}'.",
                "places": []
            }
            return f"PLACES_SEARCH_RESULT: {json.dumps(result)}"
        
        formatted_places = []
        for place in results:
            formatted_places.append({
                "place_id": place.get("place_id", ""),
                "name": place.get("name", "Unknown"),
                "address": place.get("address", ""),
                "rating": float(place.get("rating", 0)),
                "user_ratings_total": int(place.get("user_ratings_total", 0)),
                "types": place.get("types", []),
                "photo_url": place.get("photo_url", ""),
                "location": {
                    "latitude": place.get("location", {}).get("latitude"),
                    "longitude": place.get("location", {}).get("longitude")
                }
            })
        
        result = {
            "success": True,
            "message": f"Found {len(formatted_places)} places for '{query}'.",
            "places": formatted_places
        }
        return f"PLACES_SEARCH_RESULT: {json.dumps(result)}"
        
    except Exception as e:
        result = {
            "success": False,
            "message": f"Error searching places: {str(e)}",
            "places": []
        }
        return f"PLACES_SEARCH_RESULT: {json.dumps(result)}"


@tool
def get_place_info(place_id: str):
    """Fetch detailed info for a specific place by its ID."""
    try:
        details = places.get_place_details(place_id)
        
        result = {
            "success": True,
            "message": f"Retrieved details for place {place_id}",
            "place": {
                "place_id": details.get("place_id", ""),
                "name": details.get("name", ""),
                "address": details.get("address", ""),
                "website": details.get("website", ""),
                "phone": details.get("phone", ""),
                "rating": float(details.get("rating", 0)),
                "user_ratings_total": int(details.get("user_ratings_total", 0)),
                "location": details.get("location", {}),
                "photos": details.get("photos", []),
                "opening_hours": details.get("opening_hours", {})
            }
        }
        return f"PLACE_DETAILS_RESULT: {json.dumps(result)}"
        
    except Exception as e:
        result = {
            "success": False,
            "message": f"Error fetching place details: {str(e)}",
            "place": None
        }
        return f"PLACE_DETAILS_RESULT: {json.dumps(result)}"


# ================================================================
# MISTIFLY TOOLS (Flights) - FIXED
# ================================================================

@tool
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = None,
    adults: int = 1,
    cabin_class: str = "ECONOMY",
    limit: int = 5
):
    """Search for flights using Mistifly.
    
    Args:
        origin: Origin airport code (e.g., "LOS" for Lagos)
        destination: Destination airport code (e.g., "DXB" for Dubai)
        departure_date: Departure date in YYYY-MM-DD format
        return_date: Return date for round trip (optional)
        adults: Number of adult passengers
        cabin_class: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST
        limit: Max results (default 5, max 10)
    
    Returns:
        Structured JSON response with flights array
    """
    try:
        # ✅ Date validation and auto-correction
        try:
            dep_date = datetime.strptime(departure_date, "%Y-%m-%d")
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # If departure is in the past, intelligently adjust
            if dep_date < today:
                # Extract month and day
                target_month = dep_date.month
                target_day = dep_date.day
                
                # Check if this month/day has passed this year
                this_year_date = today.replace(month=target_month, day=target_day)
                
                if this_year_date >= today:
                    # Month/day is still ahead this year - use this year
                    dep_date = this_year_date
                    print(f"[Date Fix] Adjusted to this year: {dep_date.strftime('%Y-%m-%d')}")
                else:
                    # Month/day already passed this year - use next year
                    dep_date = this_year_date.replace(year=today.year + 1)
                    print(f"[Date Fix] Adjusted to next year: {dep_date.strftime('%Y-%m-%d')}")
                
                departure_date = dep_date.strftime("%Y-%m-%d")
            
            # If departure is more than 2 years in the future, normalize
            elif (dep_date - today).days > 730:  # 2 years
                target_month = dep_date.month
                target_day = dep_date.day
                this_year_date = today.replace(month=target_month, day=target_day)
                
                if this_year_date >= today:
                    dep_date = this_year_date
                else:
                    dep_date = this_year_date.replace(year=today.year + 1)
                
                departure_date = dep_date.strftime("%Y-%m-%d")
                print(f"[Date Fix] Far future normalized to {departure_date}")
            
            # Same logic for return date
            if return_date:
                ret_date = datetime.strptime(return_date, "%Y-%m-%d")
                
                # Return must be after departure
                if ret_date <= dep_date:
                    target_month = ret_date.month
                    target_day = ret_date.day
                    
                    # Try same year as departure first
                    try:
                        same_year = dep_date.replace(month=target_month, day=target_day)
                        if same_year > dep_date:
                            ret_date = same_year
                        else:
                            ret_date = same_year.replace(year=dep_date.year + 1)
                    except ValueError:
                        # Invalid date (like Feb 30), use next valid date
                        ret_date = dep_date + timedelta(days=7)
                    
                    return_date = ret_date.strftime("%Y-%m-%d")
                    print(f"[Date Fix] Return adjusted to {return_date}")
                    
        except ValueError as e:
            # If date parsing fails, let Mistifly handle it
            print(f"[Date Warning] Could not parse dates: {e}")
            pass
        
        
        # Search flights
        flights = mistifly.search_flights(
            origin=origin.upper(),
            destination=destination.upper(),
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            cabin_class=cabin_class.upper(),
            limit=limit
        )
        
        if not flights:
            result = {
                "success": False,
                "message": f"No flights found from {origin} to {destination} on {departure_date}.",
                "flights": []
            }
            result_str = f"FLIGHT_SEARCH_RESULT: {json.dumps(result)}"
            print(f"[DEBUG] Returning (no flights): {result_str}")
            return result_str
        
        # ✅ Inject search_params into EACH flight
        search_params = {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
            "return_date": return_date,
            "passengers": adults
        }
        
        for flight in flights:
            flight["search_params"] = search_params
        
        result = {
            "success": True,
            "message": f"Found {len(flights)} flights from {origin} to {destination}.",
            "flights": flights,
            "search_params": search_params
        }
        result_str = f"FLIGHT_SEARCH_RESULT: {json.dumps(result)}"
        print(f"[DEBUG] Returning (success): {result_str[:200]}...")
        return result_str
        
    except Exception as e:
        print(f"[ERROR] search_flights exception: {e}")
        import traceback
        traceback.print_exc()
        
        result = {
            "success": False,
            "message": f"Error searching flights: {str(e)}",
            "flights": []
        }
        result_str = f"FLIGHT_SEARCH_RESULT: {json.dumps(result)}"
        print(f"[DEBUG] Returning (error): {result_str}")
        return result_str


@tool
def check_flight_price(flight_id: str, raw_itinerary: dict):
    """Revalidate flight price before booking."""
    try:
        price_info = mistifly.check_price(flight_id, raw_itinerary)
        
        result = {
            "success": True,
            "message": "Price validated successfully",
            "price_info": price_info
        }
        return f"FLIGHT_PRICE_RESULT: {json.dumps(result)}"
        
    except Exception as e:
        result = {
            "success": False,
            "message": f"Error checking flight price: {str(e)}",
            "price_info": None
        }
        return f"FLIGHT_PRICE_RESULT: {json.dumps(result)}"


@tool
def book_flight(
    flight_data: dict,
    passengers: list,
    contact_email: str,
    contact_phone: str
):
    """Book a flight with passenger details.
    
    Args:
        flight_data: The selected flight object from search_flights (now has search_params!)
        passengers: List of passenger dicts with name, dob, passport, etc.
        contact_email: Contact email
        contact_phone: Contact phone (with country code)
    
    Returns:
        Booking confirmation with OrderID and PNR
    """
    try:
        # Check if we have raw_itinerary
        if "raw_itinerary" not in flight_data or not flight_data["raw_itinerary"]:
            # Extract search params (now embedded in each flight)
            search_params = flight_data.get("search_params", {})
            
            # Get flight index
            flight_id = flight_data.get("id", "flight_0")
            flight_index = int(flight_id.split("_")[1]) if "_" in flight_id else 0
            
            # Get required params
            origin = search_params.get("origin") or flight_data.get("origin")
            destination = search_params.get("destination") or flight_data.get("destination")
            departure_date = search_params.get("departure_date")
            return_date = search_params.get("return_date")
            
            if not all([origin, destination, departure_date]):
                return f"FLIGHT_BOOKING_RESULT: {json.dumps({
                    'success': False,
                    'message': 'Cannot book: missing search parameters. Please search again.',
                    'booking': None
                })}"
            
            # Re-fetch with full itinerary
            try:
                full_flight = mistifly.get_full_itinerary_for_booking(
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    return_date=return_date,
                    flight_index=flight_index
                )
                flight_data = full_flight
            except Exception as e:
                return f"FLIGHT_BOOKING_RESULT: {json.dumps({
                    'success': False,
                    'message': f'Could not retrieve full flight data: {str(e)}',
                    'booking': None
                })}"
        
        # Now we have raw_itinerary, proceed with booking
        booking_info = mistifly.book_flight(
            itinerary=flight_data,
            passengers=passengers,
            contact_email=contact_email,
            contact_phone=contact_phone
        )
        
        result = {
            "success": True,
            "message": "Flight booked successfully! Proceed with payment to issue ticket.",
            "booking": booking_info
        }
        return f"FLIGHT_BOOKING_RESULT: {json.dumps(result)}"
        
    except Exception as e:
        result = {
            "success": False,
            "message": f"Error booking flight: {str(e)}",
            "booking": None
        }
        return f"FLIGHT_BOOKING_RESULT: {json.dumps(result)}"


@tool
def issue_ticket(order_id: str):
    """Issue e-ticket after payment is completed.
    
    IMPORTANT: Only call this AFTER payment has been processed!
    """
    try:
        ticket_info = mistifly.issue_ticket(order_id)
        
        result = {
            "success": True,
            "message": "E-ticket issued successfully!",
            "ticket": ticket_info
        }
        return f"TICKET_ISSUE_RESULT: {json.dumps(result)}"
        
    except Exception as e:
        result = {
            "success": False,
            "message": f"Error issuing ticket: {str(e)}",
            "ticket": None
        }
        return f"TICKET_ISSUE_RESULT: {json.dumps(result)}"


# ================================================================
# AGENT PROMPT
# ================================================================

prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Avoya, a travel assistant helping users plan trips with flights, tours, and places.

**Core Rules:**
1. When tools return "X_RESULT:" format, extract JSON after colon and return it directly
2. For dates without years: use current year if month/day is ahead, next year if passed
3. Convert city names to airport codes (LOS=Lagos, DXB=Dubai, LHR=London, etc.)

**Tools:**
- search_flights: Find flights between cities
- search_viator_tours: Find tours/activities  
- search_places: Find hotels/restaurants/landmarks
- book_flight: Book selected flight with passenger details

**For flight queries:** Use search_flights with IATA codes and YYYY-MM-DD dates
**For tour queries:** Use search_viator_tours with destination name
**For place queries:** Use search_places with descriptive query
**For complex planning:** Combine multiple tools as needed

Be helpful and provide comprehensive travel solutions!"""),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

# ================================================================
# AGENT CONFIGURATION
# ================================================================

tools = [
    # Flights
    search_flights,
    check_flight_price,
    book_flight,
    issue_ticket,
    # Tours
    search_viator_tours,
    check_viator_availability,
    get_destination_info,
    # Places
    search_places,
    get_place_info
]

agent = create_tool_calling_agent(llm, tools, prompt)
default_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)


def create_executor_with_memory(session_id: str = None) -> AgentExecutor:
    """Create an executor with Django-based memory for a specific session."""
    if session_id:
        memory = DjangoConversationMemory(session_id=session_id, max_history_length=5)
        return AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)
    else:
        memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=5)
        return AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)

executor = default_executor