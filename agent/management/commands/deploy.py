from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run deployment tasks including migrations and database setup'

    def handle(self, *args, **options):
        self.stdout.write('Starting deployment tasks...')
        
        try:
            # Check database connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            
            # Display database info
            db_info = f"Database: {connection.vendor} - {connection.settings_dict.get('NAME', 'Unknown')}"
            self.stdout.write(
                self.style.SUCCESS(f'Database connection successful - {db_info}')
            )
            
            # Run migrations
            self.stdout.write('Running migrations...')
            call_command('migrate', verbosity=2, interactive=False)
            
            # Create superuser if it doesn't exist (optional)
            # Uncomment the following lines if you want to create a superuser during deployment
            # from django.contrib.auth.models import User
            # if not User.objects.filter(username='admin').exists():
            #     User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            #     self.stdout.write(self.style.SUCCESS('Superuser created'))
            
            self.stdout.write(
                self.style.SUCCESS('Deployment tasks completed successfully')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Deployment failed: {str(e)}')
            )
            raise
