# agent/services/monei_service.py

import os
import hmac
import hashlib
import requests
import logging
import time
from typing import Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings

# If you prefer using the official SDK (Recommended), you would import 'monei' here.
# This implementation uses the RAW REST API (custom wrapper).

logger = logging.getLogger(__name__)

class MoneiAPIError(Exception):
    """Custom exception for Monei API errors"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Monei API error {status_code}: {message}")

class MoneiService:
    """
    Wrapper for Monei payment API (v1)
    Docs: https://docs.monei.com/apis/rest/
    """
    
    BASE_URL = "https://api.monei.cc/v1"
    
    # Status mapping based on MONEI docs
    STATUS_MAP = {
        "SUCCEEDED": "PAID",
        "FAILED": "FAILED",
        "PENDING": "PROCESSING",
        "AUTHORIZED": "PROCESSING",
        "CANCELED": "CANCELLED",
        "REFUNDED": "REFUNDED",
        "PARTIALLY_REFUNDED": "PARTIALLY_REFUNDED"
    }

    def __init__(self):
        self.api_key = os.getenv("MONEI_API_KEY")
        self.account_id = os.getenv("MONEI_ACCOUNT_ID") # Sometimes required for platform headers
        self.webhook_secret = os.getenv("MONEI_WEBHOOK_SECRET")
        
        # Determine URLs from env or defaults
        self.base_domain = os.getenv("SITE_URL", "http://localhost:8000")
        self.success_url = f"{self.base_domain}/payment/success"
        self.failure_url = f"{self.base_domain}/payment/failed"
        self.cancel_url = f"{self.base_domain}/payment/cancel"
        
        if not self.api_key:
            raise ValueError("Missing MONEI_API_KEY environment variable")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MoneiPythonCustom/1.0"
        }

    # ================================================================
    # PAYMENT CREATION
    # ================================================================
    def create_payment(
        self,
        booking_id: str,
        amount: float,
        currency: str = "EUR", # Default changed to EUR as Monei is EU focused
        description: str = "Service Payment",
        customer_email: str = None,
        customer_name: str = None,
        customer_phone: str = None
    ) -> Dict:
        try:
            # 1. Convert to cents safely
            amount_cents = int(
                (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )

            # 2. Build Payload
            url = f"{self.BASE_URL}/payments"
            
            payload = {
                "amount": amount_cents,
                "currency": currency,
                "orderId": str(booking_id),
                "description": description,
                # MONEI requires specific URL params for the hosted page flow
                "callbackUrl": f"{self.base_domain}/webhooks/monei/", 
                "completeUrl": f"{self.success_url}?order_id={booking_id}",
                "failUrl": f"{self.failure_url}?order_id={booking_id}",
                "cancelUrl": f"{self.cancel_url}?order_id={booking_id}",
                "generatePaymentToken": True # Useful for recurring billing later
            }

            if customer_email or customer_name or customer_phone:
                payload["customer"] = {}
                if customer_email:
                    payload["customer"]["email"] = customer_email
                if customer_name:
                    payload["customer"]["name"] = customer_name
                if customer_phone:
                    payload["customer"]["phone"] = customer_phone

            # 3. Send Request
            # Idempotency key is good practice to prevent double charges on retry
            req_headers = {**self.headers, "Idempotency-Key": f"order_{booking_id}"}
            
            logger.info(f"[Monei] Creating payment for Order {booking_id}: {currency} {amount}")
            
            response = requests.post(url, json=payload, headers=req_headers, timeout=30)
            data = response.json()

            if not response.ok:
                raise MoneiAPIError(response.status_code, data.get("message", "Unknown error"))

            return {
                'payment_id': data.get('id'),
                'checkout_url': data.get('nextAction', {}).get('redirectUrl'),
                'status': data.get('status'),
                'amount': data.get('amount')
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"[Monei] Connection error: {e}")
            raise MoneiAPIError(503, "Payment gateway unavailable")

    # ================================================================
    # WEBHOOK VERIFICATION (CRITICAL FIX)
    # ================================================================
    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """
        Verifies the MONEI-Signature header.
        Header format: t=1600000000,v1=abcdef123456...
        """
        if not self.webhook_secret:
            logger.error("MONEI_WEBHOOK_SECRET is not set")
            return False

        try:
            # 1. Parse the header
            # Example: "t=163934823,v1=6234abcd..."
            parts = {k: v for k, v in [item.split('=') for item in signature_header.split(',')]}
            
            timestamp = parts.get('t')
            received_signature = parts.get('v1')

            if not timestamp or not received_signature:
                logger.warning("[Monei] Invalid signature header format")
                return False

            # 2. Prevent Replay Attacks (e.g., reject requests older than 5 mins)
            current_time = int(time.time())
            if current_time - int(timestamp) > 300: 
                logger.warning("[Monei] Webhook timestamp too old (replay attack?)")
                return False

            # 3. Construct Signed Payload: timestamp + "." + raw_body
            # Note: raw_body must be the exact bytes received, not parsed JSON
            signed_payload = f"{timestamp}.".encode('utf-8') + raw_body
            
            # 4. Calculate Expected HMAC
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                signed_payload,
                hashlib.sha256
            ).hexdigest()

            # 5. Secure Compare
            return hmac.compare_digest(expected_signature, received_signature)

        except Exception as e:
            logger.error(f"[Monei] Signature verification failed: {e}")
            return False

# Singleton
_monei_service = None

def get_monei_service() -> MoneiService:
    global _monei_service
    if _monei_service is None:
        _monei_service = MoneiService()
    return _monei_service