#!/usr/bin/env python
"""
Interactive Payment Flow Test for MONEI Integration
Run with: python interactive_payment_test.py
"""

import requests
import json
import time
import sys
from datetime import datetime, timedelta

# ================================================================
# ⚙️ CONFIGURATION - UPDATE THIS URL EVERY TIME YOU RESTART NGROK
# ================================================================
# ⚠️ Make sure this matches the 'Forwarding' URL in your ngrok terminal
NGROK_URL = "https://36d6a1aad490.ngrok-free.app" 
BASE_URL = f"{NGROK_URL}/api"
SESSION_ID = f"test-{int(time.time())}"

# ================================================================

def print_header(title):
    print("\n" + "=" * 70)
    print(f"🚀 {title}")
    print("=" * 70)

def check_url():
    if "your-ngrok-url" in NGROK_URL:
        print("❌ ERROR: You didn't update the NGROK_URL in the script!")
        print("   Please copy your current URL from the ngrok terminal.")
        sys.exit(1)

print_header("INTERACTIVE PAYMENT FLOW TEST")
check_url()

# ================================================================
# STEP 1: SEARCH FLIGHTS
# ================================================================
print("\n📍 STEP 1: Searching for flights (LOS -> ABV)...")
departure = (datetime.now() + timedelta(days=31)).strftime("%Y-%m-%d")

search_payload = {
    "origin": "LOS",
    "destination": "ABV", 
    "departure_date": departure,
    "adults": 1,
    "cabin_class": "ECONOMY"
}

try:
    print(f"   Sending request to: {BASE_URL}/flights/search/")
    response = requests.post(f"{BASE_URL}/flights/search/", json=search_payload, timeout=60)
    
    if response.status_code != 200:
        print(f"❌ API Error: {response.status_code}")
        print(response.text)
        sys.exit(1)
        
    search_data = response.json()
    if not search_data.get('flights'):
        print("❌ No flights found. Try different dates/routes.")
        sys.exit(1)

    flight = search_data['flights'][0]
    print(f"✅ Found {len(search_data['flights'])} flights. Selected first option:")
    print(f"   ✈️  {flight.get('airline')} | {flight.get('currency')} {flight.get('price')}")

except Exception as e:
    print(f"❌ Connection Failed: {e}")
    print("   (Is your Django server running? Is the ngrok URL correct?)")
    sys.exit(1)

# ================================================================
# STEP 2: CREATE BOOKING
# ================================================================
print("\n📍 STEP 2: Creating Booking & Payment Link...")

booking_payload = {
    "flight_data": flight,
    "passengers": [{
        "name": "Monei Tester",
        "gender": "M",
        "title": "Mr",
        "dob": "1990-01-01",
        "passport": "A12345678",
        "passport_country": "NG",
        "passport_expiry": "2030-01-01",
        "nationality": "NG"
    }],
    "contact_email": "test@monei.net",
    "contact_phone": "+2348000000000",
    "session_id": SESSION_ID,
    "cabin_class": "ECONOMY"
}

try:
    response = requests.post(f"{BASE_URL}/bookings/create/", json=booking_payload, timeout=60)
    booking_data = response.json()

    if not booking_data.get('success'):
        print(f"❌ Booking Failed: {booking_data.get('message')}")
        sys.exit(1)

    booking = booking_data['booking']
    payment = booking_data['payment']
    booking_id = booking['booking_id']
    payment_url = payment['payment_url']

    print(f"✅ Booking Created! ID: {booking_id}")
    print(f"   Amount: {payment['currency']} {payment['amount']}")

except Exception as e:
    print(f"❌ Booking Error: {e}")
    sys.exit(1)

# ================================================================
# STEP 3: MANUAL PAYMENT INSTRUCTION
# ================================================================
print_header("ACTION REQUIRED")
print(f"1. Open this URL in your browser:\n")
print(f"   👉  {payment_url}  👈\n")
print("2. Use these OFFICAL MONEI TEST credentials:")
print("   💳 Card Number:  4444 4444 4444 4406  (Visa 3DS Challenge)")
print("   📅 Expiry:       12/34")
print("   🔒 CVC:          123")
print("   👤 Name:         Test User")
print("\n3. Complete the payment flow in the browser.")
print("   (You may see a fake bank verification screen - click 'Authorise')")

# ================================================================
# STEP 4: AUTO-POLLING STATUS
# ================================================================
print("\n" + "=" * 70)
print("⏳ WAITING FOR PAYMENT (Checking every 5s)...")
print("=" * 70)

max_retries = 24  # Wait up to 2 minutes
for i in range(max_retries):
    try:
        time.sleep(5)
        res = requests.get(f"{BASE_URL}/bookings/{booking_id}/status/")
        status_data = res.json()
        
        current_status = status_data['booking']['payment_status']
        ticket_status = status_data['booking']['ticket_status']
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] Status: {current_status} | Ticket: {ticket_status}")
        
        if current_status == 'PAID':
            print("\n🎉 PAYMENT SUCCESS DETECTED!")
            if ticket_status == 'ISSUED':
                print("✅ TICKET ISSUED SUCCESSFULLY!")
            elif ticket_status == 'FAILED':
                print("⚠️  Payment received, but Ticket Issuance failed (Check Django Logs)")
            else:
                print("⏳ Payment received, waiting for ticket...")
                continue # Keep checking for ticket
            break
            
        if current_status in ['FAILED', 'CANCELLED']:
            print(f"\n❌ Payment ended with status: {current_status}")
            break
            
    except Exception as e:
        print(f"⚠️ Error checking status: {e}")

print("\n✨ Test Sequence Complete")