# Voya Agent - Deployment Guide

## Quick Deploy to Heroku

### 1. Prerequisites
- Heroku CLI installed
- Git repository initialized
- Environment variables configured

### 2. Deploy Steps

```bash
# Login to Heroku
heroku login

# Create Heroku app
heroku create your-voya-agent-app

# Set environment variables
heroku config:set OPENAI_API_KEY=your_openai_api_key
heroku config:set VIATOR_API_KEY=your_viator_api_key
heroku config:set VIATOR_AFFILIATE_ID=your_affiliate_id
heroku config:set SECRET_KEY=your_secret_key
heroku config:set DEBUG=False

# Deploy
git add .
git commit -m "Deploy Voya Agent"
git push heroku main

# Run migrations
heroku run python manage.py migrate

# Create superuser (optional)
heroku run python manage.py createsuperuser
```

### 3. Environment Variables Required

```env
OPENAI_API_KEY=your_openai_api_key_here
VIATOR_API_KEY=your_viator_api_key_here
VIATOR_AFFILIATE_ID=your_affiliate_id_here
SECRET_KEY=your_secret_key_here
DEBUG=False
```

### 4. API Endpoints

- **Chat Interface**: `https://your-app.herokuapp.com/api/chat/`
- **Health Check**: `https://your-app.herokuapp.com/api/health/`
- **Tour Search API**: `https://your-app.herokuapp.com/api/tours/search/`
- **Conversations API**: `https://your-app.herokuapp.com/api/conversations/`

### 5. Deploy to Other Platforms

#### Railway
```bash
# Install Railway CLI
npm install -g @railway/cli

# Deploy
railway login
railway init
railway up
```

#### Render
1. Connect your GitHub repository
2. Set environment variables in dashboard
3. Deploy automatically on push

#### DigitalOcean App Platform
1. Connect repository
2. Configure environment variables
3. Set build command: `pip install -r requirements-production.txt`
4. Set run command: `gunicorn voya_agent.wsgi:application`

## Features Included

✅ **Production-ready Django setup**
✅ **RESTful API with serializers**
✅ **Database models for conversations and tours**
✅ **CORS configuration for frontend integration**
✅ **Static file serving with WhiteNoise**
✅ **Logging configuration**
✅ **Health check endpoint**
✅ **Tour caching system**
✅ **Session management**

## Security Features

- CSRF protection
- XSS protection
- Content type sniffing protection
- Frame options security
- Environment variable configuration
- Production logging

## Monitoring

The application includes:
- Health check endpoint at `/api/health/`
- Structured logging to files and console
- Database query optimization
- Error handling and reporting
