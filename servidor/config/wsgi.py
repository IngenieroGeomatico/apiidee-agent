"""
Configuración WSGI para el proyecto config.

Expone el llamado WSGI como una variable a nivel de módulo llamada ``application``.

Para más información sobre este archivo, consulte
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
