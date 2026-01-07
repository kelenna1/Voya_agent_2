# agent/models.py - ENHANCED WITH PAYMENT FIELDS
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import uuid


class Conversation(models.Model):
    """Model to store chat conversations"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=255, unique=True, help_text="Unique session identifier")
    title = models.CharField(max_length=200, blank=True, help_text="Auto-generated conversation title")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.title or f"Conversation {self.session_id[:8]}"
    
    def get_message_count(self):
        return self.messages.count()
    
    def get_last_message(self):
        return self.messages.order_by('-timestamp').first()


class Message(models.Model):
    """Model to store individual messages in conversations"""
    MESSAGE_TYPES = [
        ('user', 'User Message'),
        ('assistant', 'Assistant Message'),
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.message_type}: {self.content[:50]}..."


class Tour(models.Model):
    """Model to cache tour data from Viator API"""
    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=500)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    rating = models.FloatField(default=0.0)
    review_count = models.IntegerField(default=0)
    duration = models.CharField(max_length=100, blank=True)
    destination = models.CharField(max_length=200, blank=True)
    thumbnail_url = models.URLField(blank=True)
    viator_url = models.URLField()
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-rating', '-review_count']
    
    def __str__(self):
        return f"{self.title} - ${self.price}"


# ================================================================
# PAYMENT MODELS
# ================================================================

class FlightBooking(models.Model):
    """Flight bookings with full payment integration"""
    
    PAYMENT_STATUS = [
        ('PENDING', 'Pending Payment'),
        ('PROCESSING', 'Payment Processing'),
        ('PAID', 'Payment Successful'),
        ('FAILED', 'Payment Failed'),
        ('EXPIRED', 'Booking Expired'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    TICKET_STATUS = [
        ('NOT_ISSUED', 'Not Issued'),
        ('ISSUING', 'Being Issued'),
        ('ISSUED', 'Ticket Issued'),
        ('FAILED', 'Issuance Failed'),
    ]
    
    REFUND_STATUS = [
        ('NOT_REFUNDED', 'Not Refunded'),
        ('REQUESTED', 'Refund Requested'),
        ('PROCESSING', 'Processing Refund'),
        ('REFUNDED', 'Refunded'),
        ('REJECTED', 'Refund Rejected'),
    ]
    
    # Identifiers
    booking_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # User and session
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=255, help_text="Session from conversation")
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name='flight_bookings')
    
    # Mistifly booking details
    mistifly_order_id = models.CharField(max_length=100, unique=True, help_text="Mistifly OrderID")
    pnr = models.CharField(max_length=50, blank=True, help_text="Passenger Name Record")
    booking_reference = models.CharField(max_length=100, blank=True)
    airline_pnr = models.CharField(max_length=50, blank=True)
    
    # Flight details
    origin = models.CharField(max_length=3, help_text="Origin airport IATA code")
    destination = models.CharField(max_length=3, help_text="Destination airport IATA code")
    departure_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    airline_code = models.CharField(max_length=3, blank=True)
    airline_name = models.CharField(max_length=200, blank=True)
    flight_number = models.CharField(max_length=20, blank=True)
    cabin_class = models.CharField(max_length=50, default='ECONOMY')
    
    # Passenger info
    passengers = models.JSONField(default=list, help_text="List of passenger details")
    num_passengers = models.IntegerField(default=1)
    
    # Pricing
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    # Contact info
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=50)
    
    # Payment fields
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='PENDING')
    payment_intent_id = models.CharField(max_length=255, blank=True, help_text="Monei payment ID")
    payment_url = models.URLField(blank=True, help_text="Monei checkout URL")
    payment_method = models.CharField(max_length=50, blank=True, help_text="card, bank_transfer, etc.")
    transaction_id = models.CharField(max_length=255, blank=True, help_text="Monei transaction reference")
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # Ticketing
    ticket_status = models.CharField(max_length=20, choices=TICKET_STATUS, default='NOT_ISSUED')
    ticket_numbers = models.JSONField(default=list, blank=True, help_text="E-ticket numbers")
    ticketed_at = models.DateTimeField(null=True, blank=True)
    
    # Refund fields (for future)
    refund_status = models.CharField(max_length=20, choices=REFUND_STATUS, default='NOT_REFUNDED')
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    refund_reason = models.TextField(blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    
    # Expiration
    expires_at = models.DateTimeField(help_text="Booking expires if not paid by this time")
    
    # Metadata
    raw_itinerary = models.JSONField(default=dict, help_text="Raw Mistifly itinerary data")
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['mistifly_order_id']),
            models.Index(fields=['pnr']),
            models.Index(fields=['session_id']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['payment_intent_id']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.origin} -> {self.destination} ({self.pnr or self.mistifly_order_id})"
    
    def save(self, *args, **kwargs):
        """Auto-set expiration time if not set"""
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=30)
        super().save(*args, **kwargs)
    
    def is_expired(self):
        """Check if booking has expired"""
        return timezone.now() > self.expires_at
    
    def can_be_paid(self):
        """Check if booking can be paid"""
        return (
            self.payment_status == 'PENDING' and
            not self.is_expired()
        )
    
    def mark_as_paid(self, transaction_id: str, payment_method: str = None):
        """Mark booking as paid"""
        self.payment_status = 'PAID'
        self.transaction_id = transaction_id
        self.paid_at = timezone.now()
        if payment_method:
            self.payment_method = payment_method
        self.save()
    
    def mark_as_ticketed(self, ticket_numbers: list):
        """Mark booking as ticketed"""
        self.ticket_status = 'ISSUED'
        self.ticket_numbers = ticket_numbers
        self.ticketed_at = timezone.now()
        self.save()
    
    def is_round_trip(self):
        """Check if this is a round-trip booking"""
        return self.return_date is not None
    
    def get_trip_type(self):
        """Get trip type as string"""
        return "Round Trip" if self.is_round_trip() else "One Way"


class Payment(models.Model):
    """Track all payment attempts and transactions"""
    
    PAYMENT_STATUS = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SUCCEEDED', 'Succeeded'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # Identifiers
    payment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(FlightBooking, on_delete=models.CASCADE, related_name='payment_attempts')
    
    # Monei details
    monei_payment_id = models.CharField(max_length=255, unique=True, help_text="Monei payment ID")
    monei_transaction_id = models.CharField(max_length=255, blank=True)
    
    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='PENDING')
    payment_method = models.CharField(max_length=50, blank=True)
    
    # Webhook data
    webhook_data = models.JSONField(default=dict, help_text="Raw webhook payload")
    webhook_received_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    error_code = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['monei_payment_id']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Payment {self.payment_id} - {self.status} (${self.amount})"


class WebhookLog(models.Model):
    """Log all webhook events for debugging and idempotency"""
    
    # Identifiers
    webhook_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(FlightBooking, on_delete=models.SET_NULL, null=True, blank=True, related_name='webhook_logs')
    
    # Webhook details
    event_type = models.CharField(max_length=50, help_text="payment.succeeded, payment.failed, etc.")
    monei_event_id = models.CharField(max_length=255, blank=True, help_text="Monei event ID for idempotency")
    
    # Payload
    payload = models.JSONField(help_text="Full webhook payload")
    signature = models.TextField(help_text="Webhook signature for verification")
    
    # Processing
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    received_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['monei_event_id']),
            models.Index(fields=['processed']),
        ]
    
    def __str__(self):
        return f"Webhook {self.event_type} - {self.received_at}"


class FlightSearch(models.Model):
    """Cache flight search results (optional)"""
    origin = models.CharField(max_length=3)
    destination = models.CharField(max_length=3)
    departure_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    cabin_class = models.CharField(max_length=50, default='ECONOMY')
    num_passengers = models.IntegerField(default=1)
    
    results = models.JSONField(default=list)
    result_count = models.IntegerField(default=0)
    session_id = models.CharField(max_length=255, blank=True)
    
    searched_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-searched_at']
        indexes = [
            models.Index(fields=['origin', 'destination', 'departure_date']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.origin} → {self.destination} on {self.departure_date}"
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    @classmethod
    def cleanup_expired(cls):
        """Delete expired search results"""
        cls.objects.filter(expires_at__lt=timezone.now()).delete()


class Place(models.Model):
    """Cache Google Places data (optional)"""
    place_id = models.CharField(max_length=200, unique=True)
    name = models.CharField(max_length=500)
    address = models.CharField(max_length=500, blank=True)
    rating = models.FloatField(default=0.0)
    user_ratings_total = models.IntegerField(default=0)
    types = models.JSONField(default=list)
    photo_url = models.URLField(blank=True)
    
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    opening_hours = models.JSONField(default=dict, blank=True)
    price_level = models.IntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-rating', '-user_ratings_total']
    
    def __str__(self):
        return f"{self.name} ({self.rating}★)"