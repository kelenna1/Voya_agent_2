from django.shortcuts import render
from django.utils import timezone
from django.db import transaction
from .agent import executor
from .models import Conversation, Message, Tour
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
    """Main chat interface - serves HTML page for GET, handles chat for POST"""
    
    def get(self, request, *args, **kwargs):
        """Serve the chat HTML interface"""
        return render(request, 'agent/chat.html', {'messages': []})
    
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
            
            # Invoke the AI agent
            result = executor.invoke({"input": user_input})
            ai_response = result.get("output", "Sorry, I couldn't process that.")
            
            # Save AI response
            assistant_message = Message.objects.create(
                conversation=conversation,
                message_type='assistant',
                content=ai_response,
                timestamp=timezone.now(),
                metadata={'agent_result': result}
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
        if session_id:
            return Conversation.objects.filter(session_id=session_id)
        return Conversation.objects.all()

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

@api_view(['GET'])
def health_check(request):
    """Health check endpoint for hosting platforms"""
    return Response({
        "status": "healthy",
        "service": "Voya Agent API",
        "timestamp": timezone.now().isoformat(),
        "version": "1.0.0"
    }, status=status.HTTP_200_OK)