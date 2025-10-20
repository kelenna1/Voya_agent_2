#!/usr/bin/env python
"""
Database setup script for Voya Agent
Run this script to ensure the database is properly initialized
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'voya_agent.settings')
django.setup()

from django.core.management import call_command
from django.db import connection

def setup_database():
    """Set up the database with migrations"""
    print("Setting up Voya Agent database...")
    
    try:
        # Check database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        print("✓ Database connection successful")
        
        # Run migrations
        print("Running migrations...")
        call_command('migrate', verbosity=2, interactive=False)
        print("✓ Migrations completed successfully")
        
        # Check if tables exist
        with connection.cursor() as cursor:
            # Check database type and query tables accordingly
            if 'sqlite' in connection.vendor:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()
                table_names = [table[0] for table in tables]
            else:
                # PostgreSQL
                cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
                tables = cursor.fetchall()
                table_names = [table[0] for table in tables]
            
            required_tables = [
                'agent_conversation',
                'agent_message', 
                'agent_tour'
            ]
            
            missing_tables = [table for table in required_tables if table not in table_names]
            
            if missing_tables:
                print(f"⚠ Warning: Missing tables: {missing_tables}")
                return False
            else:
                print("✓ All required tables exist")
                
        print("✓ Database setup completed successfully!")
        return True
        
    except Exception as e:
        print(f"✗ Database setup failed: {str(e)}")
        return False

if __name__ == "__main__":
    success = setup_database()
    sys.exit(0 if success else 1)
