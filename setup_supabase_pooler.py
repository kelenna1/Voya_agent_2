#!/usr/bin/env python
"""
Supabase Session Pooler setup script for Voya Agent
This script helps you configure your Supabase session pooler connection
"""

import os
import sys

def setup_supabase_pooler():
    """Set up environment variables for Supabase session pooler"""
    print("Setting up Supabase Session Pooler configuration...")
    print("\n📋 You'll need these values from your Supabase project:")
    print("1. Go to https://supabase.com/dashboard")
    print("2. Select your project")
    print("3. Go to Settings > Database")
    print("4. Scroll down to 'Connection Pooling' section")
    print("5. Copy the Session mode connection details\n")
    
    # Get Supabase session pooler connection details
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
    
    # Session pooler uses port 6543, not 5432
    host = f"db.{project_ref}.supabase.co"
    port = "6543"  # Session pooler port
    
    print(f"\n📋 Your environment variables should be:")
    print(f"DB_USER=postgres")
    print(f"DB_PASSWORD={db_password}")
    print(f"DB_HOST={host}")
    print(f"DB_PORT={port}")
    print(f"DB_NAME=postgres")
    
    # Create/update .env file
    env_file = '.env'
    env_content = []
    
    # Read existing .env file if it exists
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            env_content = f.readlines()
    
    # Remove existing DB_* variables if present
    env_content = [line for line in env_content if not any(line.startswith(prefix) for prefix in ['DB_USER=', 'DB_PASSWORD=', 'DB_HOST=', 'DB_PORT=', 'DB_NAME='])]
    
    # Add new DB variables
    env_content.extend([
        f"DB_USER=postgres\n",
        f"DB_PASSWORD={db_password}\n",
        f"DB_HOST={host}\n",
        f"DB_PORT={port}\n",
        f"DB_NAME=postgres\n"
    ])
    
    # Write updated .env file
    with open(env_file, 'w') as f:
        f.writelines(env_content)
    
    print(f"✅ Updated {env_file} with your Supabase session pooler configuration")
    print("\n🔧 Next steps:")
    print("1. Make sure your Supabase session pooler is enabled")
    print("2. Run: python setup_database.py")
    print("3. Test your API endpoints")
    
    print(f"\n⚠️  Important notes:")
    print(f"- Session pooler uses port {port}, not 5432")
    print(f"- Make sure 'Session mode' is enabled in Supabase dashboard")
    print(f"- This is different from direct database connection")
    
    return True

if __name__ == "__main__":
    setup_supabase_pooler()
