# debug_mistifly.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

print("=== MISTIFLY CONNECTIVITY TEST ===")

# 1. Load Credentials
base_url = os.getenv("MISTIFLY_BASE_URL", "https://restapidemo.myfarebox.com")
username = os.getenv("MISTIFLY_USERNAME")
password = os.getenv("MISTIFLY_PASSWORD")
account_number = os.getenv("MISTIFLY_ACCOUNT_NUMBER")

print(f"URL: {base_url}")
print(f"User: {username}")
print(f"Account Number: {account_number}") # Check if this is None!

if not account_number:
    print("\n[CRITICAL ERROR] MISTIFLY_ACCOUNT_NUMBER is missing from .env file!")
    exit()

# 2. Attempt Login
url = f"{base_url}/api/CreateSession"
payload = {
    "UserName": username,
    "Password": password,
    "AccountNumber": account_number
}

print(f"\nSending POST request to: {url}...")
try:
    response = requests.post(url, json=payload, timeout=30)
    
    print(f"Status Code: {response.status_code}")
    print("\n--- SERVER RESPONSE (RAW) ---")
    print(response.text)
    print("-----------------------------")

except Exception as e:
    print(f"Connection Failed: {e}")