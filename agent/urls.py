# agent/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ================================================================
    # MAIN CHAT INTERFACE (handles all queries - flights, tours, places)
    # ================================================================
    path('chat/', views.ChatView.as_view(), name='chat'),
    
    # ================================================================
    # CONVERSATION MANAGEMENT
    # ================================================================
    path('conversations/', views.ConversationListView.as_view(), name='conversation-list'),
    path('conversations/new/', views.create_conversation, name='create-conversation'),
    path('conversations/search/', views.ConversationSearchView.as_view(), name='conversation-search'),
    path('conversations/<int:conversation_id>/', views.ConversationDetailView.as_view(), name='conversation-detail'),
    path('conversations/<int:conversation_id>/update/', views.update_conversation, name='update-conversation'),
    path('conversations/<int:conversation_id>/delete/', views.delete_conversation, name='delete-conversation'),
    
    # ================================================================
    # FLIGHT ENDPOINTS (NEW - Direct API access)
    # ================================================================
    path('flights/search/', views.FlightSearchView.as_view(), name='flight-search'), 
    # Optional: Add these if you want direct booking endpoints later
    # path('flights/book/', views.FlightBookingView.as_view(), name='flight-book'),
    # path('flights/bookings/', views.FlightBookingListView.as_view(), name='flight-bookings'),
    # path('flights/bookings/<str:order_id>/', views.FlightBookingDetailView.as_view(), name='flight-booking-detail'),
    
    # ================================================================
    # TOUR ENDPOINTS
    # ================================================================
    path('tours/search/', views.TourSearchView.as_view(), name='tour-search'),
    
    # ================================================================
    # PLACE ENDPOINTS (Optional - if you want direct place search)
    # ================================================================
    # path('places/search/', views.PlaceSearchView.as_view(), name='place-search'),
    
    # ================================================================
    # SYSTEM
    # ================================================================
    path('health/', views.health_check, name='health-check'),
]