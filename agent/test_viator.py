# test_viator.py
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .services.viator import ViatorService

def test_viator():
    print("=== Testing Viator API ===")
    
    # Test 1: Check if API key is loaded
    api_key = os.getenv("VIATOR_API_KEY")
    print(f"VIATOR_API_KEY loaded: {'Yes' if api_key else 'No'}")
    if api_key:
        print(f"API key starts with: {api_key[:10]}...")
    
    # Test 2: Initialize service
    try:
        viator = ViatorService()
        print("✓ ViatorService initialized successfully")
    except Exception as e:
        print(f"✗ Failed to initialize ViatorService: {e}")
        return
    
    # Test 3: Basic connectivity - get destinations
    try:
        dests = viator.get_destinations()
        print(f"✓ Got {len(dests)} destinations")
        
        # Show first few destinations
        print("First 5 destinations:")
        for d in dests[:5]:
            print(f"  - {d['name']} (ID: {d['id']})")
    except Exception as e:
        print(f"✗ Failed to get destinations: {e}")
        return
    
    # Test 4: Find Rome
    try:
        rome_id = viator.resolve_destination("Rome")
        print(f"Rome ID: {rome_id}")
        
        if rome_id:
            # Test 5: Search products
            print("Testing products search...")
            tours = viator.search_products(rome_id, limit=2)
            print(f"Products results: {len(tours)} tours")
            for tour in tours:
                print(f"  - {tour['title']} - ${tour['price']}")
        else:
            print("✗ Could not find Rome destination")
            
    except Exception as e:
        print(f"✗ Search failed: {e}")

if __name__ == "__main__":
    test_viator()