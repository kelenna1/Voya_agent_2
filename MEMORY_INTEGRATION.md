# Memory Integration for Voya Agent

## Overview
The Voya Agent now has a comprehensive memory system that stores chat history in Django's database, allowing the agent to maintain context across conversations and enabling users to search through their previous interactions.

## Features

### 1. Persistent Conversation Memory
- **Django-based Storage**: All conversations are stored in the database using Django models
- **Session-based Context**: Each conversation session maintains its own memory context
- **Automatic Title Generation**: Conversations are automatically titled based on their content
- **Message History**: Complete message history is preserved for each conversation

### 2. Conversation Search
- **Content Search**: Search conversations by message content
- **Session Lookup**: Find conversations by session ID
- **Conversation Summaries**: Get quick previews of conversation topics

### 3. API Endpoints

#### Create New Conversation
```
POST /api/conversations/new/
```
Creates a new conversation with a unique session ID. Returns the new conversation details.

#### List All Conversations
```
GET /api/conversations/?limit=20
```
Returns a list of all conversations with summaries, ordered by most recent activity.
Parameters:
- `limit`: Maximum number of conversations to return (default: 20)

#### Search Conversations
```
GET /api/conversations/search/?query=tours&limit=10
```
Parameters:
- `query`: Search term to find in conversation content
- `session_id`: Specific session ID to filter by
- `limit`: Maximum number of results (default: 10)

#### Get Conversation Details
```
GET /api/conversations/{conversation_id}/
GET /api/conversations/?session_id={session_id}
```
Returns complete conversation with all messages and metadata.

#### Update Conversation
```
PUT /api/conversations/{conversation_id}/update/
Content-Type: application/json
{
    "title": "My Custom Conversation Title"
}
```
Updates the conversation title.

#### Delete Conversation
```
DELETE /api/conversations/{conversation_id}/delete/
```

### 4. Memory System Architecture

#### DjangoConversationMemory Class
- Extends LangChain's BaseMemory
- Integrates with Django models (Conversation, Message)
- Maintains session-specific context
- Automatically saves and loads conversation history

#### ConversationSearchService
- Provides search functionality
- Generates conversation summaries
- Manages conversation metadata

## Database Models

### Conversation Model
```python
class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=200, blank=True)  # Auto-generated
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
```

### Message Model
```python
class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    message_type = models.CharField(max_length=20, choices=[
        ('user', 'User Message'),
        ('assistant', 'Assistant Message'),
    ])
    content = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)
```

## Usage Examples

### 1. Chat with Memory
When a user sends a message, the system:
1. Creates or retrieves the conversation for the session
2. Saves the user message to the database
3. Creates an agent executor with memory for that session
4. Processes the message with full conversation context
5. Saves the agent's response
6. Auto-generates a conversation title

### 2. Create New Conversations
```python
import requests

# Create a new conversation
response = requests.post('http://localhost:8000/api/conversations/new/')
new_conversation = response.json()

print(f"New conversation created: {new_conversation['conversation']['session_id']}")
print(f"Conversation ID: {new_conversation['conversation']['id']}")

# Use the new session_id in chat
session_id = new_conversation['conversation']['session_id']
```

### 3. List All Conversations
```python
# Get all conversations
response = requests.get('http://localhost:8000/api/conversations/?limit=10')
conversations = response.json()

for conv in conversations['conversations']:
    print(f"Title: {conv['title']}")
    print(f"Messages: {conv['message_count']}")
    print(f"Last Activity: {conv['updated_at']}")
    print(f"Preview: {conv['preview']}")
```

### 4. Search Previous Conversations
```python
# Search for conversations about tours
conversations = ConversationSearchService.search_conversations(
    query="tours",
    limit=5
)

# Get conversation summary
for conv in conversations:
    summary = ConversationSearchService.get_conversation_summary(conv)
    print(f"Title: {summary['title']}")
    print(f"Messages: {summary['message_count']}")
    print(f"Preview: {summary['preview']}")
```

### 5. Load Conversation History
```python
# Create executor with memory for specific session
session_executor = create_executor_with_memory("session-123")

# The agent will now have access to previous messages in this session
result = session_executor.invoke({"input": "What did we discuss earlier?"})
```

## Benefits

1. **Contextual Conversations**: The agent remembers previous messages in the same session
2. **User Experience**: Users can reference past conversations and get contextual responses
3. **Search Functionality**: Easy to find previous discussions about specific topics
4. **Persistent Storage**: All conversations are saved and can be retrieved later
5. **Scalable**: Database storage can handle large numbers of conversations
6. **Flexible**: Easy to extend with additional metadata or search capabilities

## Migration
The system automatically creates the necessary database tables. Run:
```bash
python manage.py makemigrations agent
python manage.py migrate
```

## Configuration
The memory system is automatically integrated into the existing chat endpoints. No additional configuration is required - it works out of the box with the current Django setup.
