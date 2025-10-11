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
