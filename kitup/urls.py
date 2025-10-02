"""
URL configuration for kitup project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import GlobalDashboardView, frontend_landing_view, products_view, product_detail_view, cart_view, user_choice_view, get_random_clubs_ajax

urlpatterns = [
    path('admin/', admin.site.urls),

    # Authentication URLs (both namespaced and non-namespaced for compatibility)
    path('auth/', include('authentication.urls')),
    path('accounts/', include('django.contrib.auth.urls')),  # Django built-in auth URLs

    # Core app URLs
    path('clubs/', include('clubs.urls')),
    path('schools/', include('schools.urls')),
    path('dashboard/', GlobalDashboardView.as_view(), name='global-dashboard'),  # Global dashboard moved to /dashboard/

    # Frontend pages
    path('', frontend_landing_view, name='frontend-home'),  # CozaStore home page at root
    path('choose/', user_choice_view, name='user-choice'),  # Original user choice page (School/Club vs Customer)
    path('products/', products_view, name='frontend-products'),  # Products listing page
    path('product-detail/', product_detail_view, name='frontend-product-detail'),  # Product detail page
    path('cart/', cart_view, name='frontend-cart'),  # Shopping cart page
    path('ajax/random-clubs/', get_random_clubs_ajax, name='ajax-random-clubs'),  # AJAX endpoint for rotating clubs

    # =================================================================
    # API Documentation (accessible at root level)
    # =================================================================

    # Main API documentation endpoints
    path('api/', include('clubs.api_urls')),
]

# Serve media and static files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
