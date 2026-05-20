"""
ASGI entrypoint for production servers (daphne, uvicorn, etc.).

Defaults to config.settings.prod. Local development uses manage.py, which sets
config.settings.dev.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
