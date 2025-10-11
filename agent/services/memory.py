# agent/services/memory.py
from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.memory import BaseMemory
from django.utils import timezone
from ..models import Conversation, Message
import json


class DjangoConversationMemory(BaseMemory):
    """Django-based memory system that stores conversation history in the database"""
    
    memory_key: str = "chat_history"
    session_id: str = None
    max_history_length: int = 20
    
    def __init__(self, session_id: str = None, max_history_length: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.session_id = session_id
        self.max_history_length = max_history_length
    
    @property
    def memory_variables(self) -> List[str]:
        """Return the list of memory variables that this memory class maintains."""
        return [self.memory_key]
    
    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Load conversation history from database for the current session."""
        if not self.session_id:
            return {self.memory_key: []}
        
        try:
            conversation = Conversation.objects.get(session_id=self.session_id)
            messages = conversation.messages.all().order_by('timestamp')[-self.max_history_length:]
            
            # Convert Django messages to LangChain messages
            langchain_messages = []
            for message in messages:
                if message.message_type == 'user':
                    langchain_messages.append(HumanMessage(content=message.content))
                elif message.message_type == 'assistant':
                    langchain_messages.append(AIMessage(content=message.content))
            
            return {self.memory_key: langchain_messages}
            
        except Conversation.DoesNotExist:
            return {self.memory_key: []}
    
    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        """Save the conversation context to the database."""
        if not self.session_id:
            return
        
        try:
            # Get or create conversation
            conversation, created = Conversation.objects.get_or_create(
                session_id=self.session_id,
                defaults={'created_at': timezone.now()}
            )
            
            # Save user input
            if 'input' in inputs:
                Message.objects.create(
                    conversation=conversation,
                    message_type='user',
                    content=inputs['input'],
                    timestamp=timezone.now()
                )
            
            # Save AI output
            if 'output' in outputs:
                Message.objects.create(
                    conversation=conversation,
                    message_type='assistant',
                    content=outputs['output'],
                    timestamp=timezone.now(),
                    metadata={'agent_outputs': outputs}
                )
            
            # Auto-generate title if this is a new conversation or title is empty
            if created or not conversation.title:
                conversation.title = self.generate_conversation_title(conversation)
                conversation.save()
                
        except Exception as e:
            # Log error but don't fail the conversation
            print(f"Error saving conversation context: {e}")
    
    def generate_conversation_title(self, conversation: Conversation) -> str:
        """Generate a meaningful title for a conversation based on its content."""
        messages = conversation.messages.filter(message_type='user').order_by('timestamp')[:3]
        
        if not messages.exists():
            return f"Conversation {conversation.session_id[:8]}"
        
        # Combine first few user messages to generate title
        content_parts = [msg.content for msg in messages]
        combined_content = " ".join(content_parts)
        
        # Extract key topics (simple keyword extraction)
        keywords = []
        travel_keywords = ['tour', 'travel', 'visit', 'rome', 'paris', 'london', 'hotel', 'flight', 'book', 'trip', 'food', 'museum', 'walking', 'guide']
        for keyword in travel_keywords:
            if keyword.lower() in combined_content.lower():
                keywords.append(keyword.title())
        
        if keywords:
            return f"{', '.join(keywords[:2])} Discussion"
        else:
            # Fallback to first 30 characters
            return combined_content[:30] + "..." if len(combined_content) > 30 else combined_content
    
    def clear(self) -> None:
        """Clear the conversation history from database."""
        if not self.session_id:
            return
        
        try:
            conversation = Conversation.objects.get(session_id=self.session_id)
            conversation.messages.all().delete()
        except Conversation.DoesNotExist:
            pass


class ConversationSearchService:
    """Service for searching and managing conversations"""
    
    @staticmethod
    def search_conversations(query: str = None, session_id: str = None, limit: int = 10) -> List[Conversation]:
        """Search conversations by content or session ID."""
        conversations = Conversation.objects.all()
        
        if session_id:
            conversations = conversations.filter(session_id=session_id)
        
        if query:
            # Search in message content
            conversations = conversations.filter(
                messages__content__icontains=query
            ).distinct()
        
        return conversations.order_by('-updated_at')[:limit]
    
    @staticmethod
    def get_conversation_summary(conversation: Conversation) -> Dict[str, Any]:
        """Generate a summary of a conversation."""
        messages = conversation.messages.all().order_by('timestamp')
        
        if not messages.exists():
            return {
                'title': 'Empty Conversation',
                'message_count': 0,
                'last_message': None,
                'preview': 'No messages yet'
            }
        
        # Get first user message as title basis
        first_user_message = messages.filter(message_type='user').first()
        title = first_user_message.content[:50] + "..." if first_user_message and len(first_user_message.content) > 50 else (first_user_message.content if first_user_message else "Conversation")
        
        # Get last message for preview
        last_message = messages.last()
        preview = last_message.content[:100] + "..." if len(last_message.content) > 100 else last_message.content
        
        return {
            'title': title,
            'message_count': messages.count(),
            'last_message': last_message.timestamp if last_message else None,
            'preview': preview,
            'session_id': conversation.session_id
        }
    
