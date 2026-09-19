"""
ASGI entry point (plain HTTP only; there are no WebSockets — see plans/SPEC.md §3.1).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloudgene_django.settings')

application = get_asgi_application()
