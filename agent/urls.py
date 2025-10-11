from django.urls import path

from . import views

urlpatterns = [
    # Main chat interface
    path('chat/', views.ChatView.as_view(), name='chat'),
    
    # API endpoints
    path('conversations/', views.ConversationListView.as_view(), name='conversation-list'),
    path('conversations/new/', views.create_conversation, name='create-conversation'),
    path('conversations/search/', views.ConversationSearchView.as_view(), name='conversation-search'),
    path('conversations/<int:conversation_id>/', views.ConversationDetailView.as_view(), name='conversation-detail'),
    path('conversations/<int:conversation_id>/update/', views.update_conversation, name='update-conversation'),
    path('conversations/<int:conversation_id>/delete/', views.delete_conversation, name='delete-conversation'),
    path('tours/search/', views.TourSearchView.as_view(), name='tour-search'),
    path('health/', views.health_check, name='health-check'),
]