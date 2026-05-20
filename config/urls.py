from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "favicon.ico",
        RedirectView.as_view(url=f"{settings.STATIC_URL}favicon.svg", permanent=True),
    ),
    path("", include("apps.surveys.urls")),
]

if settings.DEBUG and settings.STATICFILES_DIRS:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
