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
        # ✅ FIX 1: Date validation and auto-correction
        try:
            dep_date = datetime.strptime(departure_date, "%Y-%m-%d")
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # If departure date is in the past, move to next year
            if dep_date < today:
                dep_date = dep_date.replace(year=today.year + 1)
                departure_date = dep_date.strftime("%Y-%m-%d")
                print(f"[Date Fix] Adjusted departure to {departure_date}")
            
            # Same for return date
            if return_date:
                ret_date = datetime.strptime(return_date, "%Y-%m-%d")
                if ret_date < dep_date:
                    ret_date = ret_date.replace(year=dep_date.year)
                    if ret_date < dep_date:
                        ret_date = ret_date.replace(year=dep_date.year + 1)
                    return_date = ret_date.strftime("%Y-%m-%d")
                    print(f"[Date Fix] Adjusted return to {return_date}")
                    
        except ValueError:
            # If date parsing fails, let Mistifly handle it
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
            return f"FLIGHT_SEARCH_RESULT: {json.dumps(result)}"
        
        # ✅ FIX 2: Inject search_params into EACH flight
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
        return f"FLIGHT_SEARCH_RESULT: {json.dumps(result)}"
        
    except Exception as e:
        result = {
            "success": False,
            "message": f"Error searching flights: {str(e)}",
            "flights": []
        }
        return f"FLIGHT_SEARCH_RESULT: {json.dumps(result)}"


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
    ("system", """You are Avoya, the comprehensive Voya travel assistant. You help users plan complete trips including flights, tours, and places to visit.

CRITICAL RESPONSE FORMAT RULES:
1. When a tool returns a result with a prefix like "FLIGHT_SEARCH_RESULT:", "TOUR_SEARCH_RESULT:", "PLACES_SEARCH_RESULT:", etc., you MUST:
   - Extract ONLY the JSON content after the colon
   - Return it as PURE JSON (not as a string, not escaped, not in code blocks)
   - Do NOT add any text before or after the JSON
   - Return the raw JSON object exactly as it appears

Your comprehensive capabilities:
- **Flights**: Search for flights between cities using Mistifly (search_flights)
- **Tours & Activities**: Search for tours and activities using Viator (search_viator_tours)
- **Places**: Find hotels, restaurants, and landmarks using Google Places (search_places)
- **Complete Trip Planning**: Combine all three services for comprehensive travel recommendations

MANDATORY workflow for different queries:
1. Flight queries ("find me flights to Dubai", "book a ticket to London"):
   - ALWAYS use search_flights with proper IATA codes
   - For common cities, you know the codes (LOS=Lagos, DXB=Dubai, LHR=London, JFK=New York, etc.)
   
2. Tour/activity queries ("tours in Rome", "what to do in Paris"):
   - ALWAYS use search_viator_tours
   
3. Place queries ("hotels near Eiffel Tower", "restaurants in Rome"):
   - ALWAYS use search_places
   
4. Complete trip planning ("plan a trip to Dubai", "I'm visiting London for a week"):
   - Use search_flights for transportation
   - Use search_viator_tours for activities
   - Use search_places for accommodations and dining
   - Combine all results into one comprehensive response

Expected response formats:

For flight searches:
{{{{
  "success": true/false,
  "message": "description",
  "flights": [array of flight objects with airline, price, duration, stops],
  "search_params": {{{{origin, destination, dates}}}}
}}}}

For tour searches:
{{{{
  "success": true/false,
  "message": "description",
  "tours": [array of tour objects],
  "destination": {{{{"name": "destination"}}}}
}}}}

For place searches:
{{{{
  "success": true/false,
  "message": "description",
  "places": [array of place objects]
}}}}

For combined trip planning:
{{{{
  "success": true,
  "message": "Complete trip plan",
  "flights": [flights array],
  "tours": [tours array],
  "places": [places array],
  "destination": "destination name"
}}}}

Important guidelines:
- ALWAYS search APIs before giving advice
- For flight searches, convert city names to IATA codes automatically
- When users want to book flights, explain they need to provide passenger details
- Maintain conversation context using chat history
- Be proactive: if someone asks about a destination, offer flights, tours, AND places
- ALWAYS return pure JSON when tools return *_RESULT formatted responses

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
        memory = DjangoConversationMemory(session_id=session_id, max_history_length=20)
        return AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)
    else:
        memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=20)
        return AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)


executor = default_executor