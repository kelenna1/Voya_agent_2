# agent/views.py
from django.shortcuts import render
from django.utils import timezone
from django.db import transaction
from .agent import executor, create_executor_with_memory, agent, tools
from langchain.memory import ConversationBufferWindowMemory
from langchain.agents import AgentExecutor
from .models import Conversation, Message, Tour
from .services.memory import ConversationSearchService
from .serializers import (
    ChatRequestSerializer, ChatResponseSerializer, 
    ConversationSerializer, TourSearchSerializer, 
    TourSearchResponseSerializer, TourSerializer
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from agent.utils.output_parser import parse_agent_output
import uuid
import json
import time
import hashlib
from django.core.cache import cache
from .utils.classifier import QueryClassifier
import logging
logger = logging.getLogger(__name__)
from .handlers import get_handlers
import re


class ChatView(APIView):
    """Main chat API with smart routing and multi-layer caching"""
    
    def post(self, request, *args, **kwargs):
        """Handle chat messages with intelligent routing"""
        start_time = time.time()
        serializer = ChatRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                "error": "Invalid input data",
                "details": serializer.errors,
                "success": False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user_input = serializer.validated_data['input']
            session_id = serializer.validated_data.get('session_id') or str(uuid.uuid4())
            
            # ================================================================
            # LAYER 2: QUERY CLASSIFICATION (Smart routing) - DO THIS FIRST
            # ================================================================
            classification = QueryClassifier.classify(user_input)
            
            # ================================================================
            # LAYER 1: VIEW-LEVEL CACHE (Fastest - ~5-20ms)
            # ================================================================
            # ✅ FIX: Build cache key with classification to prevent type mismatches
            cache_key = self._build_cache_key(session_id, user_input, classification)
            cached_response = cache.get(cache_key)
            
            if cached_response:
                duration = time.time() - start_time
                logger.info(f"[CACHE HIT] View-level cache hit! Duration: {duration*1000:.0f}ms, Key: {cache_key[:50]}...")
                cached_response['cached'] = True
                cached_response['duration_ms'] = int(duration * 1000)
                return Response(cached_response, status=status.HTTP_200_OK)
            logger.info(f"[CLASSIFIER] Type: {classification['type']}, Use Agent: {classification['use_agent']}, Confidence: {classification['confidence']:.2f}")
            
            # Get or create conversation
            conversation, created = Conversation.objects.get_or_create(
                session_id=session_id,
                defaults={'created_at': timezone.now()}
            )
            
            # Save user message
            user_message = Message.objects.create(
                conversation=conversation,
                message_type='user',
                content=user_input,
                timestamp=timezone.now()
            )
            
            # ================================================================
            # LAYER 3: ROUTE BASED ON CLASSIFICATION
            # ================================================================
            if classification['use_agent']:
                # Complex query - use agent
                logger.info(f"[ROUTER] Using AGENT: {classification['reason']}")
                response_data = self._handle_with_agent(
                    session_id, 
                    user_input, 
                    conversation,
                    classification
                )
            else:
                # Simple query - use direct handler (FAST PATH)
                logger.info(f"[ROUTER] Using DIRECT HANDLER: {classification['type']}")
                response_data = self._handle_with_direct_handler(
                    classification, 
                    conversation
                )
            
            # ================================================================
            # SAVE RESPONSE & CACHE
            # ================================================================
            # Save assistant message
            assistant_message = Message.objects.create(
                conversation=conversation,
                message_type='assistant',
                content=json.dumps(response_data) if isinstance(response_data, dict) else str(response_data),
                timestamp=timezone.now(),
                metadata={
                    'classification': classification,
                    'handler_type': 'agent' if classification['use_agent'] else 'direct'
                }
            )
            
            # Add metadata
            duration = time.time() - start_time
            response_data['session_id'] = session_id
            response_data['message_id'] = assistant_message.id
            response_data['duration_ms'] = int(duration * 1000)
            response_data['cached'] = False
            response_data['handler'] = 'agent' if classification['use_agent'] else 'direct'
            
            if 'type' not in response_data:
                q_type = classification.get('type')
                if q_type == 'flight':
                    response_data['type'] = 'flight_search'
                elif q_type == 'tour':
                    response_data['type'] = 'tour_search'
                elif q_type == 'place':
                    response_data['type'] = 'place_search'
                else:
                    # Fallback for generic/unknown queries
                    response_data['type'] = 'conversational'
            
            # ================================================================
            # CACHE ONLY SUCCESSFUL RESPONSES WITH VALIDATION
            # ================================================================
            # Only cache successful responses to prevent caching errors
            # Also validate that response type matches query classification
            should_cache = response_data.get('success', True) is True
            
            # ✅ FIX: Don't cache if response type doesn't match query intent
            if classification:
                query_type = classification.get('type', '')
                response_type = response_data.get('type', '')
                
                # If query was 'unknown' but response is a search type, don't cache
                if query_type == 'unknown' and response_type in ['flight_search', 'tour_search', 'place_search']:
                    should_cache = False
                    logger.warning(f"[CACHE] Skipping cache - type mismatch: query='{query_type}' vs response='{response_type}'")
            
            if should_cache:
                cache.set(cache_key, response_data, timeout=300)
                logger.info(f"[CACHE] Cached successful response (type: {response_data.get('type', 'unknown')})")
            else:
                # Cache errors for only 10 seconds to handle transient issues
                if not response_data.get('success', True):
                    cache.set(cache_key, response_data, timeout=10)
                    logger.warning(f"[CACHE] Cached error response for 10s only (success=False)")
                else:
                    logger.info(f"[CACHE] Skipped caching due to validation")
            
            logger.info(f"[PERF] Total duration: {duration*1000:.0f}ms, Type: {classification['type']}, Handler: {response_data['handler']}")
            
            return Response(response_data, status=status.HTTP_200_OK)
                
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[ERROR] Exception after {duration*1000:.0f}ms: {e}", exc_info=True)
            error_msg = self._format_error_message(str(e))
            return Response({
                "error": f"An error occurred: {error_msg}",
                "success": False,
                "duration_ms": int(duration * 1000)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _build_cache_key(self, session_id: str, user_input: str, classification: dict = None) -> str:
        """Build cache key for view-level caching"""
        # Include session for context-aware caching
        # Hash the input to keep key short
        # ✅ FIX: Include classification type in cache key to prevent type mismatches
        input_normalized = user_input.lower().strip()
        input_hash = hashlib.md5(input_normalized.encode()).hexdigest()
        
        # Include classification type if available to prevent cache collisions
        # between different query types with similar text
        if classification:
            query_type = classification.get('type', 'unknown')
            return f"chat_response:{session_id}:{query_type}:{input_hash}"
        
        return f"chat_response:{session_id}:{input_hash}"
    

    def _handle_with_direct_handler(self, classification: dict, conversation) -> dict:
        """Handle simple queries with direct handlers (NO LLM)"""
        handlers = get_handlers()
        query_type = classification['type']
        params = classification['params']
        
        try:
            if query_type == 'flight':
                result = handlers.handle_flight_search(params)
            elif query_type == 'tour':
                result = handlers.handle_tour_search(params)
            elif query_type == 'place':
                result = handlers.handle_place_search(params)
            else:
                # Unknown type - use agent
                logger.warning(f"[Direct Handler] Unknown type '{query_type}' - using agent")
                user_message = conversation.messages.filter(message_type='user').last()
                original_query = user_message.content if user_message else ""
                return self._handle_with_agent(
                    conversation.session_id,
                    original_query,
                    conversation,
                    classification  # Pass the classification we already have
                )
            
            # ✅ CHECK FOR FALLBACK FLAG
            if result.get('_use_agent_fallback'):
                logger.info(f"[Direct Handler] Fallback triggered: {result.get('reason')} - using agent")
                # Get the original user message
                user_message = conversation.messages.filter(message_type='user').last()
                original_query = user_message.content if user_message else ""
                
                return self._handle_with_agent(
                    conversation.session_id,
                    original_query,
                    conversation,
                    classification  # Pass the classification we already have
                )
            
            return result
            
        except Exception as e:
            logger.error(f"[Direct Handler] Unexpected error: {e} - falling back to agent")
            user_message = conversation.messages.filter(message_type='user').last()
            original_query = user_message.content if user_message else ""
            
            return self._handle_with_agent(
                conversation.session_id,
                original_query,
                conversation,
                classification  # Pass the classification we already have
            )
        
    def _handle_with_agent(self, session_id: str, user_input: str, conversation, classification: dict = None) -> dict:
        """Handle complex queries with LangChain agent"""
        #  FIX: For PURELY conversational queries (greetings only), don't use conversation memory
        use_memory = True
        is_pure_greeting = False
        
        if classification:
            query_type = classification.get('type', '')
            confidence = classification.get('confidence', 1.0)
            
            # Check if this is a PURE greeting (no search intent)
            # Examples: "hey", "hi", "thanks" - these should not use memory
            # Counter-examples: "hey find me restaurants" - these SHOULD use memory
            if query_type == 'unknown' and confidence < 0.5:
                # Check if user_input is PURELY greeting (very short, no search keywords)
                user_input_lower = user_input.lower().strip()
                
                # List of pure greeting patterns
                pure_greetings = [
                    r'^\s*(hey+|hi+|hello+|howdy|sup|yo)\s*$',
                    r'^\s*(thanks?|thank you|thx)\s*$',
                    r'^\s*(ok|okay|sure|alright|cool)\s*$',
                    r'^\s*(yes|yeah|yep|nope|no)\s*$',
                ]
                
                is_pure_greeting = any(re.search(pattern, user_input_lower, re.IGNORECASE) for pattern in pure_greetings)
                
                if is_pure_greeting:
                    use_memory = False
                    logger.info(f"[AGENT] Pure greeting detected, disabling memory: '{user_input[:50]}'")
        
        # Create executor with or without memory based on query type
        if use_memory:
            session_executor = create_executor_with_memory(session_id)
        else:
            # Create executor without memory for fresh context
            memory = ConversationBufferWindowMemory(memory_key="chat_history", return_messages=True, k=0)
            session_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)
        
        # Invoke agent
        result = session_executor.invoke({"input": user_input})
        ai_response = result.get("output", "Sorry, I couldn't process that.")
        
        logger.info(f"[AGENT] Raw response: {ai_response[:200]}...")
        
        #  USE THE NEW PARSER
        structured_response = parse_agent_output(ai_response)
        
        logger.info(f"[AGENT] Parsed response type: {structured_response.get('type')}, success: {structured_response.get('success')}")
        
        # FIX: ONLY override if this was a PURE greeting (no search intent)
        # If query had search intent (like "hey find me restaurants"), DON'T override
        if is_pure_greeting and classification and classification.get('type') == 'unknown':
            response_type = structured_response.get('type', '')
            # Only override if agent returned a search type for a PURE greeting
            if response_type in ['flight_search', 'tour_search', 'place_search']:
                logger.warning(f"[AGENT] Pure greeting got search response '{response_type}'. Overriding to conversational.")
                structured_response['type'] = 'conversational'
                # Remove search-specific fields
                for field in ['flights', 'tours', 'places']:
                    if field in structured_response:
                        del structured_response[field]
                # Keep the message if it exists, otherwise use output
                if 'output' not in structured_response and 'message' in structured_response:
                    structured_response['output'] = structured_response['message']
        
        return structured_response


    
    
    def _format_error_message(self, error_str: str) -> str:
        """Format error messages for user display"""
        if "no such table" in error_str.lower():
            return "Database not properly initialized. Please contact administrator."
        elif "database is locked" in error_str.lower():
            return "Database is temporarily unavailable. Please try again."
        elif "mistifly" in error_str.lower():
            return "Flight service temporarily unavailable. Please try again."
        elif "viator" in error_str.lower():
            return "Tour service temporarily unavailable. Please try again."
        return error_str


class FlightSearchView(APIView):
    """Direct flight search endpoint (bypasses agent)"""
    
    def post(self, request, *args, **kwargs):
        """Search for flights directly using Mistifly API"""
        try:
            from .services.mistifly import MistiflyService
            
            # Extract search parameters
            origin = request.data.get('origin', '').upper()
            destination = request.data.get('destination', '').upper()
            departure_date = request.data.get('departure_date')
            return_date = request.data.get('return_date')
            adults = int(request.data.get('adults', 1))
            cabin_class = request.data.get('cabin_class', 'ECONOMY').upper()
            
            # Validate required fields
            if not all([origin, destination, departure_date]):
                return Response({
                    'success': False,
                    'message': 'Origin, destination, and departure date are required',
                    'flights': []
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Search flights
            mistifly = MistiflyService()
            flights = mistifly.search_flights(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                adults=adults,
                cabin_class=cabin_class
            )
            
            # ✅ FIX: ALWAYS inject search_params into each flight
            search_params = {
                'origin': origin,
                'destination': destination,
                'departure_date': departure_date,
                'return_date': return_date,
                'passengers': adults,
                'cabin_class': cabin_class
            }
            
            for flight in flights:
                if isinstance(flight, dict):
                    flight['search_params'] = search_params
            
            return Response({
                'success': True,
                'message': f"Found {len(flights)} flights",
                'flights': flights,
                'search_params': search_params,
                'type': 'flight_search'
            }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response({
                'success': False,
                'message': f"Error searching flights: {str(e)}",
                'flights': []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConversationListView(ListAPIView):
    """API endpoint to list conversations"""
    serializer_class = ConversationSerializer
    
    def get_queryset(self):
        session_id = self.request.query_params.get('session_id')
        limit = int(self.request.query_params.get('limit', 20))
        
        queryset = Conversation.objects.all()
        
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        
        return queryset.order_by('-updated_at')[:limit]
    
    def list(self, request, *args, **kwargs):
        """Override list to provide enhanced conversation data"""
        queryset = self.get_queryset()
        
        conversations_data = []
        for conv in queryset:
            summary = ConversationSearchService.get_conversation_summary(conv)
            conversation_data = {
                'id': conv.id,
                'session_id': conv.session_id,
                'title': conv.title,
                'created_at': conv.created_at,
                'updated_at': conv.updated_at,
                'message_count': conv.get_message_count(),
                'last_message': conv.get_last_message().timestamp if conv.get_last_message() else None,
                'preview': summary.get('preview', ''),
                'url': f"/api/conversations/{conv.id}/"
            }
            conversations_data.append(conversation_data)
        
        return Response({
            'success': True,
            'conversations': conversations_data,
            'total': len(conversations_data)
        }, status=status.HTTP_200_OK)


class TourSearchView(APIView):
    """API endpoint for direct tour search"""
    
    def post(self, request, *args, **kwargs):
        """Search for tours using Viator API"""
        serializer = TourSearchSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                "error": "Invalid search parameters",
                "details": serializer.errors,
                "success": False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            from .services.viator import ViatorService
            
            search_params = serializer.validated_data
            viator = ViatorService()
            
            tours = viator.search_tours(
                query=search_params.get('query'),
                destination=search_params['destination'],
                start_date=search_params.get('date'),
                page_size=search_params['limit']
            )
            
            # Cache tours in database
            cached_tours = []
            for tour_data in tours:
                tour, created = Tour.objects.update_or_create(
                    code=tour_data['code'],
                    defaults={
                        'title': tour_data['title'],
                        'price': tour_data['price'],
                        'rating': tour_data['rating'],
                        'review_count': tour_data['reviewCount'],
                        'duration': tour_data.get('duration', ''),
                        'destination': search_params['destination'],
                        'thumbnail_url': tour_data.get('thumbnail', ''),
                        'viator_url': tour_data['url'],
                        'updated_at': timezone.now()
                    }
                )
                cached_tours.append(tour)
            
            tour_serializer = TourSerializer(cached_tours, many=True)
            response_serializer = TourSearchResponseSerializer(data={
                'success': True,
                'message': f"Found {len(cached_tours)} tours",
                'tours': tour_serializer.data,
                'destination': search_params['destination'],
                'search_params': search_params
            })
            
            if response_serializer.is_valid():
                return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': True,
                    'message': f"Found {len(cached_tours)} tours",
                    'tours': tour_serializer.data,
                    'destination': search_params['destination']
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response({
                'success': False,
                'message': f"Error searching tours: {str(e)}",
                'tours': []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConversationSearchView(APIView):
    """API endpoint for searching conversations"""
    
    def get(self, request, *args, **kwargs):
        """Search conversations by query or session ID"""
        query = request.query_params.get('query', '')
        session_id = request.query_params.get('session_id', '')
        limit = int(request.query_params.get('limit', 10))
        
        try:
            conversations = ConversationSearchService.search_conversations(
                query=query if query else None,
                session_id=session_id if session_id else None,
                limit=limit
            )
            
            conversation_summaries = []
            for conv in conversations:
                summary = ConversationSearchService.get_conversation_summary(conv)
                summary['id'] = conv.id
                summary['created_at'] = conv.created_at
                summary['updated_at'] = conv.updated_at
                conversation_summaries.append(summary)
            
            return Response({
                'success': True,
                'conversations': conversation_summaries,
                'total': len(conversation_summaries),
                'query': query,
                'session_id': session_id
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f"Error searching conversations: {str(e)}",
                'conversations': []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConversationDetailView(APIView):
    """API endpoint for getting conversation details and messages"""
    
    def get(self, request, conversation_id=None, *args, **kwargs):
        """Get conversation details and all messages"""
        session_id = request.query_params.get('session_id')
        
        try:
            if conversation_id:
                conversation = Conversation.objects.get(id=conversation_id)
            elif session_id:
                conversation = Conversation.objects.get(session_id=session_id)
            else:
                return Response({
                    'success': False,
                    'error': 'Either conversation_id or session_id must be provided'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            messages = conversation.messages.all().order_by('timestamp')
            
            message_data = []
            for message in messages:
                message_data.append({
                    'id': message.id,
                    'type': message.message_type,
                    'content': message.content,
                    'timestamp': message.timestamp,
                    'metadata': message.metadata
                })
            
            summary = ConversationSearchService.get_conversation_summary(conversation)
            
            return Response({
                'success': True,
                'conversation': {
                    'id': conversation.id,
                    'session_id': conversation.session_id,
                    'created_at': conversation.created_at,
                    'updated_at': conversation.updated_at,
                    'summary': summary,
                    'messages': message_data
                }
            }, status=status.HTTP_200_OK)
            
        except Conversation.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Conversation not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'error': f"Error retrieving conversation: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def create_conversation(request):
    """Create a new conversation"""
    try:
        new_session_id = str(uuid.uuid4())
        
        conversation = Conversation.objects.create(
            session_id=new_session_id,
            created_at=timezone.now()
        )
        
        return Response({
            'success': True,
            'message': 'New conversation created successfully',
            'conversation': {
                'id': conversation.id,
                'session_id': conversation.session_id,
                'title': conversation.title,
                'created_at': conversation.created_at,
                'message_count': 0
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': f"Error creating conversation: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_conversation(request, conversation_id):
    """Update conversation title or other metadata"""
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        
        new_title = request.data.get('title', '').strip()
        
        if new_title:
            conversation.title = new_title
            conversation.save()
            
            return Response({
                'success': True,
                'message': 'Conversation updated successfully',
                'conversation': {
                    'id': conversation.id,
                    'session_id': conversation.session_id,
                    'title': conversation.title,
                    'updated_at': conversation.updated_at
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'error': 'Title is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
    except Conversation.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Conversation not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': f"Error updating conversation: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_conversation(request, conversation_id):
    """Delete a conversation and all its messages"""
    try:
        conversation = Conversation.objects.get(id=conversation_id)
        conversation.delete()
        
        return Response({
            'success': True,
            'message': 'Conversation deleted successfully'
        }, status=status.HTTP_200_OK)
        
    except Conversation.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Conversation not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'error': f"Error deleting conversation: {str(e)}"
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def health_check(request):
    """Health check endpoint for hosting platforms"""
    return Response({
        "status": "healthy",
        "service": "Voya Agent API",
        "timestamp": timezone.now().isoformat(),
        "version": "1.0.0",
        "services": {
            "flights": "mistifly",
            "tours": "viator",
            "places": "google"
        }
    }, status=status.HTTP_200_OK)

# agent/views.py - ADD THESE NEW VIEWS

from .services.monei import get_monei_service
from agent.models import FlightBooking, Payment, WebhookLog
from datetime import timedelta

# ... (keep all your existing views) ...

# ================================================================
# BOOKING & PAYMENT VIEWS
# ================================================================

# agent/views.py - UPDATED CreateFlightBookingView (replace the existing one)

class CreateFlightBookingView(APIView):
    """
    Create flight booking and generate payment link
    
    FIXED: Added revalidation step before booking
    """
    
    def post(self, request, *args, **kwargs):
        start_time = time.time()
        
        try:
            # ================================================================
            # STEP 1: Validate Input
            # ================================================================
            flight_data = request.data.get('flight_data')
            passengers = request.data.get('passengers', [])
            contact_email = request.data.get('contact_email')
            contact_phone = request.data.get('contact_phone')
            session_id = request.data.get('session_id', str(uuid.uuid4()))
            
            # ✅ FIX: Allow cabin_class to be passed directly (not just in search_params)
            cabin_class = request.data.get('cabin_class', 'ECONOMY')
            
            if not all([flight_data, passengers, contact_email, contact_phone]):
                return Response({
                    'success': False,
                    'message': 'Missing required fields: flight_data, passengers, contact_email, contact_phone'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if not passengers:
                return Response({
                    'success': False,
                    'message': 'At least one passenger is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate email format
            import re
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', contact_email):
                return Response({
                    'success': False,
                    'message': 'Invalid email format'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"[Booking] Creating booking for {contact_email}, {len(passengers)} passenger(s)")
            
            # ================================================================
            # STEP 2: Extract Search Parameters (ROBUST)
            # ================================================================
            from agent.services.mistifly import MistiflyService
            mistifly = MistiflyService()
            
            # ✅ FIX: Build search_params from multiple sources with fallbacks
            search_params = flight_data.get('search_params', {})
            
            # Extract from search_params OR flight_data directly
            origin = search_params.get('origin') or flight_data.get('origin')
            destination = search_params.get('destination') or flight_data.get('destination')
            departure_date = search_params.get('departure_date') or flight_data.get('departure_date')
            return_date = search_params.get('return_date') or flight_data.get('return_date')
            
            # ✅ ADDITIONAL FIX: Extract date from departure_time if departure_date is missing
            if not departure_date and flight_data.get('departure_time'):
                # departure_time format: "2026-01-17T10:30:00"
                departure_date = flight_data['departure_time'].split('T')[0]
                logger.info(f"[Booking] Extracted departure_date from departure_time: {departure_date}")
            
            # Validate we have required fields
            if not all([origin, destination, departure_date]):
                logger.error(f"[Booking] Missing route info. Flight data: {flight_data.keys()}")
                return Response({
                    'success': False,
                    'message': 'Flight data missing origin, destination, or departure_date. Please search again.',
                    'debug': {
                        'has_search_params': bool(search_params),
                        'flight_keys': list(flight_data.keys()),
                        'departure_time': flight_data.get('departure_time')
                    }
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"[Booking] Route: {origin} -> {destination} on {departure_date}")
            
            # ================================================================
            # STEP 3: Get Full Itinerary (if not already present)
            # ================================================================
            if 'raw_itinerary' not in flight_data or not flight_data['raw_itinerary']:
                # Need to re-fetch full itinerary
                flight_id = flight_data.get('id', 'flight_0')
                flight_index = int(flight_id.split('_')[1]) if '_' in flight_id else 0
                
                logger.info(f"[Booking] Re-fetching full itinerary for flight {flight_index}")
                
                try:
                    full_flight = mistifly.get_full_itinerary_for_booking(
                        origin=origin,
                        destination=destination,
                        departure_date=departure_date,
                        return_date=return_date,
                        flight_index=flight_index,
                        adults=len(passengers),
                        cabin_class=cabin_class
                    )
                    flight_data = full_flight
                except Exception as e:
                    logger.error(f"[Booking] Re-fetch failed: {e}")
                    return Response({
                        'success': False,
                        'message': f"Could not retrieve flight data: {str(e)}. Please search again."
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # ================================================================
            # STEP 3.5: REVALIDATE FLIGHT (CRITICAL FIX)
            # ================================================================
            logger.info("[Booking] Revalidating flight before booking...")
            
            try:
                # This gets the "Bookable" version with the SearchIdentifier/FareSourceCode
                bookable_itinerary = mistifly.revalidate_flight(flight_data['raw_itinerary'])
                
                # Update the flight data with the new bookable itinerary
                flight_data['raw_itinerary'] = bookable_itinerary
                
                # Optional: Update price if it changed during revalidation
                new_price = bookable_itinerary.get("AirItineraryPricingInfo", {}).get("ItinTotalFare", {}).get("TotalFare", {}).get("Amount")
                if new_price:
                    flight_data['price'] = float(new_price)
                    logger.info(f"[Booking] Price confirmed: {new_price}")
                    
            except Exception as e:
                logger.error(f"[Booking] Revalidation failed: {e}")
                return Response({
                    'success': False,
                    'message': f"Flight is no longer available or price has changed: {str(e)}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # ================================================================
            # STEP 4: Book with Mistifly
            # ================================================================
            logger.info("[Booking] Creating Mistifly reservation...")
            
            booking_response = mistifly.book_flight(
                itinerary=flight_data,
                passengers=passengers,
                contact_email=contact_email,
                contact_phone=contact_phone
            )
            
            mistifly_order_id = booking_response.get('order_id')
            pnr = booking_response.get('pnr')
            
            if not mistifly_order_id:
                return Response({
                    'success': False,
                    'message': 'Failed to create Mistifly reservation',
                    'error': booking_response.get('message')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            logger.info(f"[Booking] Mistifly reservation created: {mistifly_order_id}")
            
            # ================================================================
            # STEP 5: Create FlightBooking Record
            # ================================================================
            # Parse departure_date to date object if it's a string
            if isinstance(departure_date, str):
                from datetime import datetime as dt
                departure_date = dt.strptime(departure_date, "%Y-%m-%d").date()
            
            if return_date and isinstance(return_date, str):
                return_date = dt.strptime(return_date, "%Y-%m-%d").date()
            
            booking = FlightBooking.objects.create(
                session_id=session_id,
                mistifly_order_id=mistifly_order_id,
                pnr=pnr,
                booking_reference=booking_response.get('booking_reference', ''),
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                airline_code=flight_data.get('airline'),
                flight_number=flight_data.get('flight_number'),
                cabin_class=cabin_class,
                passengers=passengers,
                num_passengers=len(passengers),
                total_amount=booking_response.get('total_amount', flight_data.get('price', 0)),
                currency=booking_response.get('currency', flight_data.get('currency', 'USD')),
                contact_email=contact_email,
                contact_phone=contact_phone,
                raw_itinerary=flight_data.get('raw_itinerary', {}),
                payment_status='PENDING',
                ticket_status='NOT_ISSUED',
                expires_at=timezone.now() + timedelta(minutes=30)
            )
            
            logger.info(f"[Booking] FlightBooking created: {booking.booking_id}")
            
            # ================================================================
            # STEP 6: Create Monei Payment
            # ================================================================
            try:
                monei = get_monei_service()
                
                payment_result = monei.create_payment(
                    booking_id=str(booking.booking_id),
                    amount=float(booking.total_amount),
                    currency=booking.currency,
                    description=f"Flight {booking.origin} to {booking.destination}",
                    customer_email=contact_email,
                    customer_phone=contact_phone
                )
                
                # Update booking with payment info
                booking.payment_intent_id = payment_result['payment_id']
                booking.payment_url = payment_result['checkout_url']
                booking.save()
                
                # Create Payment record
                Payment.objects.create(
                    booking=booking,
                    monei_payment_id=payment_result['payment_id'],
                    amount=booking.total_amount,
                    currency=booking.currency,
                    status='PENDING'
                )
                
                logger.info(f"[Booking] Payment created: {payment_result['payment_id']}")
                
            except Exception as e:
                logger.error(f"[Booking] Payment creation failed: {e}")
                return Response({
                    'success': False,
                    'message': f"Booking created but payment setup failed: {str(e)}",
                    'booking_id': str(booking.booking_id),
                    'can_retry': True
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # ================================================================
            # STEP 7: Return Success Response
            # ================================================================
            duration = time.time() - start_time
            
            response_data = {
                'success': True,
                'message': 'Booking created successfully! Complete payment to confirm.',
                'booking': {
                    'booking_id': str(booking.booking_id),
                    'mistifly_order_id': booking.mistifly_order_id,
                    'pnr': booking.pnr,
                    'origin': booking.origin,
                    'destination': booking.destination,
                    'departure_date': booking.departure_date.isoformat(),
                    'return_date': booking.return_date.isoformat() if booking.return_date else None,
                    'passengers': booking.num_passengers,
                    'total_amount': float(booking.total_amount),
                    'currency': booking.currency,
                    'payment_status': booking.payment_status,
                    'expires_at': booking.expires_at.isoformat(),
                    'expires_in_minutes': 30
                },
                'payment': {
                    'payment_url': booking.payment_url,
                    'payment_id': booking.payment_intent_id,
                    'amount': float(booking.total_amount),
                    'currency': booking.currency
                },
                'next_steps': [
                    f"1. Complete payment within 30 minutes",
                    f"2. Redirect user to: {booking.payment_url}",
                    f"3. After payment, user will be redirected back",
                    f"4. Check payment status at: /api/bookings/{booking.booking_id}/status/"
                ],
                'duration_ms': int(duration * 1000)
            }
            
            logger.info(f"[Booking] Complete! Duration: {duration*1000:.0f}ms")
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[Booking] Error after {duration*1000:.0f}ms: {e}", exc_info=True)
            return Response({
                'success': False,
                'message': f"Booking creation failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        
class BookingStatusView(APIView):
    """
    Get booking status and payment info
    GET /api/bookings/<booking_id>/status/
    """
    
    def get(self, request, booking_id, *args, **kwargs):
        """Get current booking status"""
        try:
            booking = FlightBooking.objects.get(booking_id=booking_id)
            
            # Check if expired
            is_expired = booking.is_expired()
            if is_expired and booking.payment_status == 'PENDING':
                booking.payment_status = 'EXPIRED'
                booking.save()
            
            response_data = {
                'success': True,
                'booking': {
                    'booking_id': str(booking.booking_id),
                    'pnr': booking.pnr,
                    'origin': booking.origin,
                    'destination': booking.destination,
                    'payment_status': booking.payment_status,
                    'ticket_status': booking.ticket_status,
                    'is_expired': is_expired,
                    'can_pay': booking.can_be_paid(),
                    'payment_url': booking.payment_url if booking.can_be_paid() else None,
                    'total_amount': float(booking.total_amount),
                    'currency': booking.currency,
                    'expires_at': booking.expires_at.isoformat(),
                    'created_at': booking.created_at.isoformat(),
                    'paid_at': booking.paid_at.isoformat() if booking.paid_at else None,
                    'ticketed_at': booking.ticketed_at.isoformat() if booking.ticketed_at else None,
                    'ticket_numbers': booking.ticket_numbers
                }
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except FlightBooking.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Booking not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[Booking Status] Error: {e}")
            return Response({
                'success': False,
                'message': f"Error retrieving booking: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RetryPaymentView(APIView):
    """
    Generate new payment link for existing booking
    POST /api/bookings/<booking_id>/retry-payment/
    """
    
    def post(self, request, booking_id, *args, **kwargs):
        """Retry payment for a booking"""
        try:
            booking = FlightBooking.objects.get(booking_id=booking_id)
            
            # Validate booking can be paid
            if not booking.can_be_paid():
                return Response({
                    'success': False,
                    'message': f"Booking cannot be paid. Status: {booking.payment_status}, Expired: {booking.is_expired()}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create new payment
            monei = get_monei_service()
            
            payment_result = monei.create_payment(
                booking_id=str(booking.booking_id),
                amount=float(booking.total_amount),
                currency=booking.currency,
                description=f"Flight {booking.origin} to {booking.destination} (Retry)",
                customer_email=booking.contact_email,
                customer_phone=booking.contact_phone
            )
            
            # Update booking
            booking.payment_intent_id = payment_result['payment_id']
            booking.payment_url = payment_result['checkout_url']
            booking.save()
            
            # Create new Payment record
            Payment.objects.create(
                booking=booking,
                monei_payment_id=payment_result['payment_id'],
                amount=booking.total_amount,
                currency=booking.currency,
                status='PENDING'
            )
            
            return Response({
                'success': True,
                'message': 'New payment link generated',
                'payment_url': booking.payment_url,
                'payment_id': booking.payment_intent_id
            }, status=status.HTTP_200_OK)
            
        except FlightBooking.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Booking not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"[Retry Payment] Error: {e}")
            return Response({
                'success': False,
                'message': f"Error generating payment link: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
# agent/views.py - ADD WEBHOOK HANDLER

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json

@method_decorator(csrf_exempt, name='dispatch')
class MoneiWebhookView(APIView):
    """
    Handle Monei payment webhooks
    POST /api/webhooks/monei/
    
    CRITICAL: This endpoint processes payments and issues tickets.
    """
    
    def post(self, request, *args, **kwargs):
        start_time = time.time()
        
        try:
            # ================================================================
            # 1. VERIFY SIGNATURE (CRITICAL SECURITY FIX)
            # ================================================================
            # FIX: MONEI uses 'MONEI-Signature', not 'X-Monei-Signature'
            signature = request.headers.get('MONEI-Signature', '')
            payload = request.body
            
            monei = get_monei_service()
            
            # Use the secure verification method from the service
            if not monei.verify_webhook_signature(payload, signature):
                logger.warning(f"[Webhook] Invalid signature received from IP: {request.META.get('REMOTE_ADDR')}")
                return Response({'success': False, 'message': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
            
            # ================================================================
            # 2. PARSE DATA
            # ================================================================
            try:
                webhook_data = json.loads(payload.decode('utf-8'))
            except json.JSONDecodeError:
                return Response({'success': False, 'message': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
            
            event_type = webhook_data.get('type')
            monei_event_id = webhook_data.get('id')
            
            # MONEI structure: data is inside 'data' key, orderId is inside that
            payment_data = webhook_data.get('data', {})
            order_id = payment_data.get('orderId')
            
            # ================================================================
            # 3. IDEMPOTENCY CHECK
            # ================================================================
            if WebhookLog.objects.filter(monei_event_id=monei_event_id, processed=True).exists():
                return Response({'success': True, 'message': 'Already processed'}, status=status.HTTP_200_OK)

            # ================================================================
            # 4. FIND BOOKING
            # ================================================================
            try:
                booking = FlightBooking.objects.get(booking_id=order_id)
            except FlightBooking.DoesNotExist:
                logger.error(f"[Webhook] Booking {order_id} not found.")
                # Return 200 OK to stop MONEI from retrying dead webhooks
                return Response({'success': True, 'message': 'Booking not found'}, status=status.HTTP_200_OK)

            # ================================================================
            # 5. CREATE LOG & PROCESS
            # ================================================================
            # Create log entry (unprocessed)
            log_entry = WebhookLog.objects.create(
                booking=booking,
                monei_event_id=monei_event_id,
                event_type=event_type,
                payload=webhook_data,
                signature=signature
            )

            # Process Event
            if event_type == 'payment.succeeded':
                self._handle_payment_success(booking, payment_data)
            elif event_type == 'payment.failed':
                self._handle_payment_failure(booking, payment_data)
            elif event_type == 'payment.canceled' or event_type == 'payment.cancelled':
                self._handle_payment_cancelled(booking, payment_data)
            else:
                logger.warning(f"[Webhook] Unhandled event type: {event_type}")
            
            # Mark Processed
            log_entry.processed = True
            log_entry.processed_at = timezone.now()
            log_entry.save()

            duration = time.time() - start_time
            logger.info(f"[Webhook] Processed {event_type} in {duration*1000:.0f}ms")

            return Response({'success': True}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"[Webhook] System Error: {e}", exc_info=True)
            # Return 500 to tell MONEI to retry later (standard behavior)
            return Response({'success': False}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_payment_success(self, booking, payment_data):
        """Handle successful payment - Mark Paid & Attempt Ticketing"""
        logger.info(f"[Webhook] Payment SUCCESS for booking {booking.booking_id}")
        
        transaction_id = payment_data.get('id')
        payment_method = payment_data.get('paymentMethod', {}).get('type', 'card')
        
        # 1. Update DB to PAID immediately
        booking.mark_as_paid(transaction_id, payment_method)
        
        # Update Payment Record
        Payment.objects.filter(booking=booking, monei_payment_id=transaction_id).update(
            status='SUCCEEDED',
            monei_transaction_id=transaction_id,
            payment_method=payment_method,
            webhook_received_at=timezone.now()
        )
        
        # 2. Attempt Ticketing (Wrapped in Try/Except to protect Payment Status)
        try:
            from agent.services.mistifly import MistiflyService
            mistifly = MistiflyService()
            
            logger.info(f"[Webhook] Issuing ticket for order {booking.mistifly_order_id}")
            ticket_result = mistifly.issue_ticket(booking.mistifly_order_id)
            
            booking.mark_as_ticketed(ticket_result.get('ticket_numbers', []))
            
            if ticket_result.get('airline_pnr'):
                booking.airline_pnr = ticket_result['airline_pnr']
                booking.save()
                
            logger.info(f"[Webhook] Ticket issued: {ticket_result.get('ticket_numbers')}")
            
        except Exception as e:
            # CRITICAL: Do NOT raise error here. The user has paid. 
            # We must return 200 OK to MONEI and handle ticketing manually.
            logger.error(f"[Ticketing] Failed for booking {booking.booking_id}: {e}")
            booking.ticket_status = 'FAILED'
            booking.notes = f"PAID BUT TICKET FAILED: {str(e)}"
            booking.save()

    def _handle_payment_failure(self, booking, payment_data):
        """Handle failed payment"""
        logger.info(f"[Webhook] Payment FAILED for booking {booking.booking_id}")
        
        booking.payment_status = 'FAILED'
        booking.save()
        
        error_code = payment_data.get('error', {}).get('code', '')
        error_message = payment_data.get('error', {}).get('message', 'Payment failed')
        
        Payment.objects.filter(booking=booking, monei_payment_id=payment_data.get('id')).update(
            status='FAILED',
            error_code=error_code,
            error_message=error_message,
            webhook_received_at=timezone.now()
        )

    def _handle_payment_cancelled(self, booking, payment_data):
        """Handle cancelled payment"""
        logger.info(f"[Webhook] Payment CANCELLED for booking {booking.booking_id}")
        
        booking.payment_status = 'CANCELLED'
        booking.save()
        
        Payment.objects.filter(booking=booking, monei_payment_id=payment_data.get('id')).update(
            status='CANCELLED',
            webhook_received_at=timezone.now()
        )