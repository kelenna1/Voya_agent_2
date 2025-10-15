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
    """Main chat API, handles chat for POST"""
    
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
            
            # Clean non-serializable objects from result
            def safe_json(value):
                try:
                    json.dumps(value)
                    return value
                except TypeError:
                    if isinstance(value, dict):
                        return {k: safe_json(v) for k, v in value.items()}
                    elif isinstance(value, list):
                        return [safe_json(v) for v in value]
                    elif hasattr(value, "content"):
                        return str(value.content)
                    else:
                        return str(value)

            clean_result = safe_json(result)

            assistant_message = Message.objects.create(
                conversation=conversation,
                message_type='assistant',
                content=ai_response,
                timestamp=timezone.now(),
                metadata={'agent_result': clean_result}
            )

            
            # Return structured response
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
            return Response({
                "error": f"An error occurred: {str(e)}",
                "success": False
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
        
        # Generate summaries for each conversation
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
            
            # Perform search
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
            
            # Serialize response
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
            
            # Generate summaries for each conversation
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
            
            # Get all messages for this conversation
            messages = conversation.messages.all().order_by('timestamp')
            
            # Serialize messages
            message_data = []
            for message in messages:
                message_data.append({
                    'id': message.id,
                    'type': message.message_type,
                    'content': message.content,
                    'timestamp': message.timestamp,
                    'metadata': message.metadata
                })
            
            # Generate conversation summary
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
        # Generate a new session ID
        new_session_id = str(uuid.uuid4())
        
        # Create new conversation
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
        
        # Get new title from request data
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
        "version": "1.0.0"
    }, status=status.HTTP_200_OK)