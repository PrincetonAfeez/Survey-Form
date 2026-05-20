""" WSGI entrypoint for production servers (gunicorn, uwsgi, etc.) """

""" Defaults to config.settings.prod. Local development uses manage.py, which sets config.settings.dev. """

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
