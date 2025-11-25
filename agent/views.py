# agent/views.py
from django.shortcuts import render
from django.utils import timezone
from django.db import transaction
from .agent import executor, create_executor_with_memory
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
import uuid
import json


class ChatView(APIView):
    """Main chat API with support for tours, places, and flights"""
    
    def post(self, request, *args, **kwargs):
        """Handle chat messages with proper serialization and database storage"""
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
            
            # Create executor with memory for this session
            session_executor = create_executor_with_memory(session_id)
            
            # Invoke the AI agent with memory
            result = session_executor.invoke({"input": user_input})
            ai_response = result.get("output", "Sorry, I couldn't process that.")
            
            # Check if the response contains structured data
            structured_response = self._extract_structured_response(ai_response)
            
            # Clean non-serializable objects from result
            clean_result = self._safe_json(result)

            # Save assistant message
            assistant_message = Message.objects.create(
                conversation=conversation,
                message_type='assistant',
                content=ai_response,
                timestamp=timezone.now(),
                metadata={'agent_result': clean_result}
            )

            # Return structured response if available, otherwise conversational
            if structured_response:
                return Response(structured_response, status=status.HTTP_200_OK)
            else:
                response_serializer = ChatResponseSerializer(data={
                    'output': ai_response,
                    'success': True,
                    'session_id': session_id,
                    'message_id': assistant_message.id
                })
                
                if response_serializer.is_valid():
                    return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
                else:
                    return Response({
                        "output": ai_response,
                        "success": True,
                        "session_id": session_id,
                        "message_id": assistant_message.id
                    }, status=status.HTTP_200_OK)
                
        except Exception as e:
            error_msg = self._format_error_message(str(e))
            return Response({
                "error": f"An error occurred: {error_msg}",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _extract_structured_response(self, ai_response: str):
        """Extract structured JSON from AI response if present"""
        result_types = [
            "TOUR_SEARCH_RESULT:",
            "PLACES_SEARCH_RESULT:",
            "PLACE_DETAILS_RESULT:",
            "FLIGHT_SEARCH_RESULT:",
            "FLIGHT_PRICE_RESULT:",
            "FLIGHT_BOOKING_RESULT:",
            "AVAILABILITY_RESULT:",
            "DESTINATION_INFO_RESULT:",
            "COMPLETE_TRIP_RESULT:"
        ]
        
        for result_type in result_types:
            if result_type in ai_response:
                try:
                    json_start = ai_response.find(result_type) + len(result_type)
                    json_part = ai_response[json_start:].strip()
                    return json.loads(json_part)
                except json.JSONDecodeError:
                    continue
        
        # Check if response is pure JSON
        if ai_response.strip().startswith('{'):
            try:
                return json.loads(ai_response)
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _safe_json(self, value):
        """Recursively clean non-serializable objects"""
        try:
            json.dumps(value)
            return value
        except TypeError:
            if isinstance(value, dict):
                return {k: self._safe_json(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [self._safe_json(v) for v in value]
            elif hasattr(value, "content"):
                return str(value.content)
            else:
                return str(value)
    
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
            
            return Response({
                'success': True,
                'message': f"Found {len(flights)} flights",
                'flights': flights,
                'search_params': {
                    'origin': origin,
                    'destination': destination,
                    'departure_date': departure_date,
                    'return_date': return_date,
                    'passengers': adults
                }
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