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
    # FLIGHT ENDPOINTS (Direct API access)
    # ================================================================
    path('flights/search/', views.FlightSearchView.as_view(), name='flight-search'),
    
    # ================================================================
    # BOOKING & PAYMENT ENDPOINTS (NEW!)
    # ================================================================
    path('bookings/create/', views.CreateFlightBookingView.as_view(), name='create-booking'),
    path('bookings/<uuid:booking_id>/status/', views.BookingStatusView.as_view(), name='booking-status'),
    path('bookings/<uuid:booking_id>/retry-payment/', views.RetryPaymentView.as_view(), name='retry-payment'),
    
    # ================================================================
    # WEBHOOK ENDPOINT (CRITICAL - Monei will call this!)
    # ================================================================
    path('webhooks/monei/', views.MoneiWebhookView.as_view(), name='monei-webhook'),
    
    # ================================================================
    # TOUR ENDPOINTS
    # ================================================================
    path('tours/search/', views.TourSearchView.as_view(), name='tour-search'),
    
    # ================================================================
    # PLACE ENDPOINTS (Optional - uncomment if needed)
    # ================================================================
    # path('places/search/', views.PlaceSearchView.as_view(), name='place-search'),
    
    # ================================================================
    # SYSTEM
    # ================================================================
    path('health/', views.health_check, name='health-check'),
]