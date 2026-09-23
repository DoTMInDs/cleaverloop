from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic.base import RedirectView
from apps.studio.views import HomeView, ExploreView
from apps.billing.views import PricingPlansView

urlpatterns = [
    path('favicon.ico', RedirectView.as_view(url='/static/images/logo/favicon.png', permanent=True)),
    path('admin/', admin.site.urls),
    
    # Dedicated Homepage, Explore Feed & Pricing
    path('', HomeView.as_view(), name='home'),
    path('explore/', ExploreView.as_view(), name='explore'),
    path('pricing/', PricingPlansView.as_view(), name='pricing'),

    # CleaverLoop Applications
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('accounts/', include('allauth.urls')),
    path('credits/', include('apps.credits.urls', namespace='credits')),

    path('billing/', include('apps.billing.urls', namespace='billing')),
    path('studio/', include('apps.studio.urls', namespace='studio')),
    path('characters/', include('apps.characters.urls', namespace='characters')),
    path('projects/', include('apps.projects.urls', namespace='projects')),
    path('generations/', include('apps.generations.urls', namespace='generations')),
    path('editor/', include('apps.editor.urls', namespace='editor')),
    path('agent/', include('apps.ai.urls', namespace='agent')),
    path('voices/', include('apps.voices.urls', namespace='voices')),
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

if settings.DEBUG:
    # Include django_browser_reload URLs only in DEBUG mode
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
