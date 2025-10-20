#!/usr/bin/env python
"""
Supabase setup script for Voya Agent
This script helps you configure your Supabase database connection
"""

import os
import sys

def setup_supabase_env():
    """Set up environment variables for Supabase"""
    print("Setting up Supabase configuration...")
    print("\nYou'll need to get these values from your Supabase project dashboard:")
    print("1. Go to https://supabase.com/dashboard")
    print("2. Select your project")
    print("3. Go to Settings > Database")
    print("4. Copy the connection string or individual values\n")
    
    # Get Supabase connection details
    project_url = input("Enter your Supabase project URL (e.g., https://xxxxx.supabase.co): ").strip()
    if not project_url:
        print("❌ Project URL is required")
        return False
    
    # Extract project reference from URL
    if '.supabase.co' in project_url:
        project_ref = project_url.replace('https://', '').replace('.supabase.co', '')
    else:
        project_ref = input("Enter your Supabase project reference: ").strip()
    
    if not project_ref:
        print("❌ Project reference is required")
        return False
    
    db_password = input("Enter your database password: ").strip()
    if not db_password:
        print("❌ Database password is required")
        return False
    
    # Construct the DATABASE_URL
    database_url = f"postgresql://postgres:{db_password}@db.{project_ref}.supabase.co:5432/postgres"
    
    print(f"\n📋 Your DATABASE_URL is:")
    print(f"DATABASE_URL={database_url}")
    
    # Create/update .env file
    env_file = '.env'
    env_content = []
    
    # Read existing .env file if it exists
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            env_content = f.readlines()
    
    # Remove existing DATABASE_URL if present
    env_content = [line for line in env_content if not line.startswith('DATABASE_URL=')]
    
    # Add new DATABASE_URL
    env_content.append(f"DATABASE_URL={database_url}\n")
    
    # Write updated .env file
    with open(env_file, 'w') as f:
        f.writelines(env_content)
    
    print(f"✅ Updated {env_file} with your Supabase configuration")
    print("\n🔧 Next steps:")
    print("1. Make sure your Supabase database is accessible")
    print("2. Run: python setup_database.py")
    print("3. Test your API endpoints")
    
    return True

if __name__ == "__main__":
    setup_supabase_env()
