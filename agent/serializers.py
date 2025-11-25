# agent/serializers.py
from rest_framework import serializers
from datetime import date
# UPDATE THIS LINE - Add the new models:
from .models import Conversation, Message, Tour, FlightBooking, FlightSearch, Place


# ================================================================
# KEEP ALL YOUR EXISTING SERIALIZERS (Don't change these!)
# ================================================================

class MessageSerializer(serializers.ModelSerializer):
    """Serializer for chat messages"""
    
    class Meta:
        model = Message
        fields = ['id', 'message_type', 'content', 'timestamp', 'metadata']
        read_only_fields = ['id', 'timestamp']


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for conversations with messages"""
    messages = MessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = ['id', 'session_id', 'created_at', 'updated_at', 'messages', 'message_count']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_message_count(self, obj):
        return obj.messages.count()


class TourSerializer(serializers.ModelSerializer):
    """Serializer for tour data"""
    
    class Meta:
        model = Tour
        fields = [
            'id', 'code', 'title', 'price', 'rating', 'review_count',
            'duration', 'destination', 'thumbnail_url', 'viator_url',
            'description', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ChatRequestSerializer(serializers.Serializer):
    """Serializer for chat API requests"""
    input = serializers.CharField(max_length=2000, help_text="User message input")
    session_id = serializers.CharField(max_length=255, required=False, help_text="Session identifier")
    
    def validate_input(self, value):
        if not value.strip():
            raise serializers.ValidationError("Input cannot be empty")
        return value.strip()


class ChatResponseSerializer(serializers.Serializer):
    """Serializer for chat API responses"""
    output = serializers.CharField(help_text="AI agent response")
    success = serializers.BooleanField(help_text="Whether the request was successful")
    session_id = serializers.CharField(help_text="Session identifier")
    message_id = serializers.IntegerField(help_text="Message ID in database")
    error = serializers.CharField(required=False, help_text="Error message if success is False")


class TourSearchSerializer(serializers.Serializer):
    """Serializer for tour search requests"""
    query = serializers.CharField(max_length=200, required=False, default="tour")
    destination = serializers.CharField(max_length=200, help_text="Destination city or country")
    date = serializers.CharField(required=False, help_text="Start date for tours (YYYY-MM-DD)")
    limit = serializers.IntegerField(min_value=1, max_value=20, default=5, help_text="Number of results to return")
    
    def validate_destination(self, value):
        if not value.strip():
            raise serializers.ValidationError("Destination cannot be empty")
        return value.strip().title()


class TourSearchResponseSerializer(serializers.Serializer):
    """Serializer for tour search responses"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    tours = TourSerializer(many=True, required=False)
    destination = serializers.CharField(required=False)
    search_params = serializers.DictField(required=False)


# ================================================================
# ADD EVERYTHING BELOW THIS LINE (New Flight & Place Serializers)
# ================================================================

class FlightBookingSerializer(serializers.ModelSerializer):
    """Serializer for flight bookings"""
    trip_type = serializers.SerializerMethodField()
    
    class Meta:
        model = FlightBooking
        fields = [
            'id', 'order_id', 'pnr', 'booking_reference', 'airline_pnr',
            'origin', 'destination', 'departure_date', 'return_date',
            'airline_code', 'airline_name', 'flight_number', 'cabin_class',
            'passengers', 'num_passengers', 'total_amount', 'currency',
            'contact_email', 'contact_phone', 'ticket_numbers', 'ticketed_at',
            'status', 'trip_type', 'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'ticketed_at']
    
    def get_trip_type(self, obj):
        return obj.get_trip_type()


class FlightSearchSerializer(serializers.Serializer):
    """Serializer for flight search requests"""
    origin = serializers.CharField(
        max_length=3, 
        help_text="Origin airport IATA code (e.g., LOS, JFK)"
    )
    destination = serializers.CharField(
        max_length=3, 
        help_text="Destination airport IATA code (e.g., DXB, LHR)"
    )
    departure_date = serializers.DateField(
        help_text="Departure date (YYYY-MM-DD)"
    )
    return_date = serializers.DateField(
        required=False, 
        allow_null=True,
        help_text="Return date for round trip (YYYY-MM-DD)"
    )
    adults = serializers.IntegerField(
        min_value=1, 
        max_value=9, 
        default=1,
        help_text="Number of adult passengers (12+ years)"
    )
    children = serializers.IntegerField(
        min_value=0, 
        max_value=8, 
        default=0,
        help_text="Number of children (2-11 years)"
    )
    infants = serializers.IntegerField(
        min_value=0, 
        max_value=4, 
        default=0,
        help_text="Number of infants (0-2 years)"
    )
    cabin_class = serializers.ChoiceField(
        choices=['ECONOMY', 'PREMIUM_ECONOMY', 'BUSINESS', 'FIRST'],
        default='ECONOMY',
        help_text="Cabin class preference"
    )
    
    def validate_origin(self, value):
        """Validate and uppercase origin code"""
        if not value or len(value) != 3:
            raise serializers.ValidationError("Origin must be a 3-letter IATA code")
        return value.upper()
    
    def validate_destination(self, value):
        """Validate and uppercase destination code"""
        if not value or len(value) != 3:
            raise serializers.ValidationError("Destination must be a 3-letter IATA code")
        return value.upper()
    
    def validate(self, data):
        """Cross-field validation"""
        # Check that origin and destination are different
        if data.get('origin') == data.get('destination'):
            raise serializers.ValidationError(
                "Origin and destination cannot be the same"
            )
        
        # Validate return date is after departure date
        if data.get('return_date') and data.get('departure_date'):
            if data['return_date'] <= data['departure_date']:
                raise serializers.ValidationError(
                    "Return date must be after departure date"
                )
        
        # Validate total passengers doesn't exceed limit
        total_passengers = (
            data.get('adults', 1) + 
            data.get('children', 0) + 
            data.get('infants', 0)
        )
        if total_passengers > 9:
            raise serializers.ValidationError(
                "Total passengers cannot exceed 9"
            )
        
        return data


class FlightSearchResponseSerializer(serializers.Serializer):
    """Serializer for flight search responses"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    flights = serializers.ListField(child=serializers.DictField(), required=False)
    search_params = serializers.DictField(required=False)


class PassengerSerializer(serializers.Serializer):
    """Serializer for passenger details"""
    FirstName = serializers.CharField(max_length=100)
    LastName = serializers.CharField(max_length=100)
    Gender = serializers.ChoiceField(choices=['M', 'F'])
    DateOfBirth = serializers.DateField(help_text="YYYY-MM-DD format")
    PassportNumber = serializers.CharField(max_length=50)
    PassportExpiryDate = serializers.DateField(help_text="YYYY-MM-DD format")
    PassportIssuingCountry = serializers.CharField(max_length=2, help_text="2-letter country code")
    Nationality = serializers.CharField(max_length=2, help_text="2-letter country code")
    PassengerType = serializers.ChoiceField(
        choices=['ADT', 'CHD', 'INF'],
        default='ADT',
        help_text="ADT=Adult, CHD=Child, INF=Infant"
    )
    
    def validate_DateOfBirth(self, value):
        """Validate date of birth is in the past"""
        if value >= date.today():
            raise serializers.ValidationError("Date of birth must be in the past")
        return value
    
    def validate_PassportExpiryDate(self, value):
        """Validate passport hasn't expired"""
        if value <= date.today():
            raise serializers.ValidationError("Passport has expired")
        return value


class FlightBookingRequestSerializer(serializers.Serializer):
    """Serializer for flight booking requests"""
    flight_id = serializers.CharField(help_text="Flight ID from search results")
    raw_itinerary = serializers.DictField(help_text="Raw flight itinerary data")
    passengers = PassengerSerializer(many=True)
    contact_email = serializers.EmailField()
    contact_phone = serializers.CharField(max_length=50)
    
    def validate_passengers(self, value):
        """Validate passenger list is not empty"""
        if not value:
            raise serializers.ValidationError("At least one passenger is required")
        return value


class FlightBookingResponseSerializer(serializers.Serializer):
    """Serializer for flight booking responses"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    booking = serializers.DictField(required=False)


class PlaceSerializer(serializers.ModelSerializer):
    """Serializer for place data"""
    location = serializers.SerializerMethodField()
    
    class Meta:
        model = Place
        fields = [
            'id', 'place_id', 'name', 'address', 'rating', 'user_ratings_total',
            'types', 'photo_url', 'location', 'website', 'phone', 
            'opening_hours', 'price_level', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_location(self, obj):
        """Return location as dict"""
        if obj.latitude and obj.longitude:
            return {
                'latitude': obj.latitude,
                'longitude': obj.longitude
            }
        return None


class PlaceSearchSerializer(serializers.Serializer):
    """Serializer for place search requests"""
    query = serializers.CharField(
        max_length=500,
        help_text="Search query (e.g., 'hotels in London', 'restaurants near Eiffel Tower')"
    )
    limit = serializers.IntegerField(
        min_value=1, 
        max_value=20, 
        default=5,
        help_text="Number of results to return"
    )
    
    def validate_query(self, value):
        if not value.strip():
            raise serializers.ValidationError("Query cannot be empty")
        return value.strip()


class PlaceSearchResponseSerializer(serializers.Serializer):
    """Serializer for place search responses"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    places = PlaceSerializer(many=True, required=False)


class CompleteTripPlanSerializer(serializers.Serializer):
    """Serializer for complete trip planning responses (flights + tours + places)"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    destination = serializers.CharField()
    flights = serializers.ListField(child=serializers.DictField(), required=False)
    tours = TourSerializer(many=True, required=False)
    places = PlaceSerializer(many=True, required=False)
    trip_dates = serializers.DictField(required=False)
    estimated_budget = serializers.DictField(required=False)