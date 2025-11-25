# agent/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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
        """Get the number of messages in this conversation"""
        return self.messages.count()
    
    def get_last_message(self):
        """Get the last message in this conversation"""
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
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional data like tool calls, etc.")
    
    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.message_type}: {self.content[:50]}..."


class Tour(models.Model):
    """Model to cache tour data from Viator API"""
    code = models.CharField(max_length=50, unique=True, help_text="Viator product code")
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
# NEW FLIGHT MODELS
# ================================================================

class FlightBooking(models.Model):
    """Model to store flight bookings from Mistifly API"""
    BOOKING_STATUS = [
        ('pending', 'Pending Payment'),
        ('confirmed', 'Confirmed'),
        ('ticketed', 'Ticketed'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ]
    
    # User and session info
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=255, help_text="Session from conversation")
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name='flight_bookings')
    
    # Mistifly order details
    order_id = models.CharField(max_length=100, unique=True, help_text="Mistifly OrderID")
    pnr = models.CharField(max_length=50, blank=True, help_text="Passenger Name Record")
    booking_reference = models.CharField(max_length=100, blank=True)
    airline_pnr = models.CharField(max_length=50, blank=True, help_text="Airline-specific PNR")
    
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
    
    # Ticketing
    ticket_numbers = models.JSONField(default=list, blank=True, help_text="E-ticket numbers")
    ticketed_at = models.DateTimeField(null=True, blank=True)
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=BOOKING_STATUS, default='pending')
    raw_itinerary = models.JSONField(default=dict, help_text="Raw Mistifly itinerary data")
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_id']),
            models.Index(fields=['pnr']),
            models.Index(fields=['session_id']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.origin} → {self.destination} ({self.pnr or self.order_id})"
    
    def mark_as_ticketed(self, ticket_numbers):
        """Mark booking as ticketed with ticket numbers"""
        self.status = 'ticketed'
        self.ticket_numbers = ticket_numbers
        self.ticketed_at = timezone.now()
        self.save()
    
    def is_round_trip(self):
        """Check if this is a round-trip booking"""
        return self.return_date is not None
    
    def get_trip_type(self):
        """Get trip type as string"""
        return "Round Trip" if self.is_round_trip() else "One Way"


class FlightSearch(models.Model):
    """Model to cache flight search results (optional but useful)"""
    # Search parameters
    origin = models.CharField(max_length=3)
    destination = models.CharField(max_length=3)
    departure_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    cabin_class = models.CharField(max_length=50, default='ECONOMY')
    num_passengers = models.IntegerField(default=1)
    
    # Search results
    results = models.JSONField(default=list, help_text="Cached flight results")
    result_count = models.IntegerField(default=0)
    
    # Session tracking
    session_id = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    searched_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(help_text="When this cache expires")
    
    class Meta:
        ordering = ['-searched_at']
        indexes = [
            models.Index(fields=['origin', 'destination', 'departure_date']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.origin} → {self.destination} on {self.departure_date}"
    
    def is_expired(self):
        """Check if search cache is expired"""
        return timezone.now() > self.expires_at
    
    @classmethod
    def cleanup_expired(cls):
        """Delete expired search results"""
        cls.objects.filter(expires_at__lt=timezone.now()).delete()


class Place(models.Model):
    """Model to cache Google Places data (optional)"""
    place_id = models.CharField(max_length=200, unique=True)
    name = models.CharField(max_length=500)
    address = models.CharField(max_length=500, blank=True)
    rating = models.FloatField(default=0.0)
    user_ratings_total = models.IntegerField(default=0)
    types = models.JSONField(default=list)
    photo_url = models.URLField(blank=True)
    
    # Location
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    # Contact info
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    
    # Additional details
    opening_hours = models.JSONField(default=dict, blank=True)
    price_level = models.IntegerField(null=True, blank=True, help_text="1-4 price range")
    
    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-rating', '-user_ratings_total']
    
    def __str__(self):
        return f"{self.name} ({self.rating}★)"