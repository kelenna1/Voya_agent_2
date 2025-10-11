from rest_framework import serializers
from .models import Conversation, Message, Tour

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
    date = serializers.DateField(required=False, help_text="Start date for tours (YYYY-MM-DD)")
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
