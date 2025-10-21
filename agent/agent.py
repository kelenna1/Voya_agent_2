# agent/agent.py
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory
import os
from dotenv import load_dotenv
from agent.services.viator import ViatorService
from agent.services.memory import DjangoConversationMemory
from datetime import datetime, timedelta
from agent.services.google import GooglePlacesService

places = GooglePlacesService()

# Load environment variables
load_dotenv()

# Initialize LLM  
llm = ChatOpenAI(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))

# Initialize ViatorService
viator = ViatorService()

# Define tools
@tool
def search_viator_tours(query: str = "tour", destination: str = "Rome", date: str = None, limit: int = 5):
    """Search for tours based on query, destination, and date.
    
    Args:
        query: The type of tour (e.g., "walking tour", "food tour", "museum tour")
        destination: The city or destination name (e.g., "Rome", "Paris", "London")
        date: Start date in YYYY-MM-DD format (defaults to 7 days from now)
        limit: Maximum number of results to return (default 5)
    
    Returns:
        List of tours with code, title, price, duration, rating, url, and thumbnail
    """
    try:
        if not date:
            date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        tours = viator.search_tours(query, destination, date, limit)
        
        if not tours:
            return {
                "success": False,
                "message": f"No tours found for '{query}' in {destination} starting {date}. The sandbox may have limited data. Try broader search terms or different destinations ",
                "tours": []
            }
        
        return {
            "success": True,
            "message": f"Found {len(tours)} tours",
            "tours": tours
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error searching tours: {str(e)}",
            "tours": []
        }

@tool
def check_viator_availability(product_code: str):
    """Check availability schedules for a specific tour product.
    
    Args:
        product_code: The Viator product code from search results
    
    Returns:
        List of available schedules with dates and times, or error message
    """
    try:
        schedules = viator.check_availability(product_code)
        
        if not schedules:
            return {
                "success": False,
                "message": f"No availability data found for product {product_code}. This may be a sandbox limitation.",
                "schedules": []
            }
        
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
    """Get the Viator destination ID for a given city or destination name.
    
    Args:
        destination_name: Name of the destination (e.g., "Rome", "Paris", "London")
    
    Returns:
        Destination ID if found, or error message
    """
    try:
        dest_id = viator.resolve_destination(destination_name)
        
        if not dest_id:
            return {
                "success": False,
                "message": f"Could not find destination '{destination_name}'. Try: Rome, Paris, London, or other major cities."
            }
        
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
    
@tool
def search_places(query: str, limit: int = 5):
    """Search for places using Google Places API.
    Example: 'restaurants in Rome', 'hotels near Eiffel Tower'"""
    try:
        results = places.search_places(query, limit)
        if not results:
            return {"success": False, "message": "No places found.", "places": []}
        return {"success": True, "message": f"Found {len(results)} places", "places": results}
    except Exception as e:
        return {"success": False, "message": str(e), "places": []}


@tool
def get_place_info(place_id: str):
    """Fetch detailed info for a specific place by its ID."""
    try:
        details = places.get_place_details(place_id)
        return {"success": True, "details": details}
    except Exception as e:
        return {"success": False, "message": str(e)}

# Define prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", """You arE Avoya, the Voya travel assistant. You help users discover and explore tours using Viator's extensive catalog of real tours worldwide.

CRITICAL: You MUST use the available tools to search Viator's database for real tours. Do NOT provide general travel advice or recommendations without searching the Viator API first.

Your capabilities:
- Search for tours by activity and destination using Viator
- Search for places, landmarks, hotels, or restaurants using Google Places
- Combine both to give full travel recommendations (e.g., tours + nearby attractions)
- Search for tours by activity type, destination, and dates using search_viator_tours
- Check tour availability schedules using check_viator_availability  
- Get destination information using get_destination_info
- Provide detailed tour information (pricing, duration, ratings, reviews)
- Generate booking links for users to complete their reservations

MANDATORY workflow for tour requests:
1. ALWAYS use search_viator_tours tool when users ask about tours, destinations, or activities
2. If you need destination info first, use get_destination_info
3. Format your response with tour details in this EXACT format:

1. **Tour Name**
**Price:** $XX.XX
**Rating:** X.X (X reviews)  
**Duration:** X hours
[More Details & Booking](viator_url)

2. **Tour Name**
**Price:** $XX.XX
**Rating:** X.X (X reviews)  
**Duration:** X hours
[More Details & Booking](viator_url)

4. Provide 3-5 real tours from Viator API results
5. If no tours found, explain this and suggest alternative searches

Important guidelines:
- NEVER give general travel advice without searching Viator first
- Always ask for clarification if the request is vague, state what else you need to perform a smooth search
- Help the developer debug exactly what's wrong by telling him what your response was and if you're getting result from the viator api and do this only if you the user says "programmer is here", you'd welcome him as the programmer and help debug if there's issues
- When users want to book, provide the direct Viator URL for the tour
- You can search and recommend but cannot complete bookings (users book on Viator)
- Use chat history to maintain context and personalize recommendations

Be friendly, enthusiastic, and helpful. Make travel planning feel easy and exciting!"""),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])
# Create agent and executor (memory will be set per session)
tools = [search_viator_tours, check_viator_availability, get_destination_info, search_places,
    get_place_info]
agent = create_tool_calling_agent(llm, tools, prompt)

# Default executor without memory (memory will be added per session)
default_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

def create_executor_with_memory(session_id: str = None) -> AgentExecutor:
    """Create an executor with Django-based memory for a specific session."""
    if session_id:
        memory = DjangoConversationMemory(session_id=session_id, max_history_length=20)
        return AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)
    else:
        # Fallback to default memory for backward compatibility
        memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=20)
        return AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)

# Keep the default executor for backward compatibility
executor = default_executor

# Test the agent with conversation
if __name__ == "__main__":
    test_conversation = [
        "find me tours in rome",
        "came to rome for a weekend, can you plan a trip or tour for me around the city",
        "let's say food related... just for the next 3 days"
    ]
    
    print("=== Testing Voya Agent (Captain-V) ===\n")
    
    for user_input in test_conversation:
        print(f"\nUser: {user_input}")
        print("-" * 60)
        result = executor.invoke({"input": user_input})
        print(f"\nCaptain-V: {result['output']}")
        print("=" * 60)