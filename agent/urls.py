from django.urls import path

from . import views

urlpatterns = [
    # Main chat interface
    path('chat/', views.ChatView.as_view(), name='chat'),
    
    # API endpoints
    path('conversations/', views.ConversationListView.as_view(), name='conversation-list'),
    path('tours/search/', views.TourSearchView.as_view(), name='tour-search'),
    path('health/', views.health_check, name='health-check'),
]