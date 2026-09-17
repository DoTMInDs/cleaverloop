from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Root redirects to Studio Dashboard
    path('', RedirectView.as_view(pattern_name='studio:dashboard', permanent=False), name='root'),

    # CleverLoop Applications
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('credits/', include('apps.credits.urls', namespace='credits')),
    path('billing/', include('apps.billing.urls', namespace='billing')),
    path('studio/', include('apps.studio.urls', namespace='studio')),
    path('characters/', include('apps.characters.urls', namespace='characters')),
    path('projects/', include('apps.projects.urls', namespace='projects')),
    path('generations/', include('apps.generations.urls', namespace='generations')),
    path('editor/', include('apps.editor.urls', namespace='editor')),
    path('agent/', include('apps.ai.urls', namespace='agent')),
    path('adminpanel/', include('apps.adminpanel.urls', namespace='adminpanel')),

    # REST APIs & Universal Webhooks
    path('api/generations/', include('apps.generations.api_urls')),
    path('api/projects/', include('apps.projects.api_urls')),
    path('api/characters/', include('apps.characters.api_urls')),
    path('api/providers/', include('apps.providers.api_urls')),
    path('api/webhooks/', include('apps.generations.webhook_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
