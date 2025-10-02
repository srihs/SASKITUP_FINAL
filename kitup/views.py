from django.shortcuts import render
from django.views.generic import TemplateView
from clubs.models_lotto import LottoClub, LottoClubCategory, LottoProduct
from clubs.models_sas import SASClub, SASProduct
from clubs.models_tus import TUSSchool


class GlobalDashboardView(TemplateView):
    """Main global dashboard for the SASKITUP admin system"""
    template_name = 'dashboard/global_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Basic statistics for the dashboard using separate models
        context['total_lotto_clubs'] = LottoClub.objects.filter(is_active=True).count()
        context['total_sas_clubs'] = SASClub.objects.filter(is_active=True).count()
        context['total_clubs'] = context['total_lotto_clubs'] + context['total_sas_clubs']

        # Category counts from separate models
        lotto_categories = LottoClubCategory.objects.filter(product_count__gt=0).count()
        context['total_categories'] = lotto_categories

        # Product counts from separate models
        lotto_products = LottoProduct.objects.filter(stock_status__in=['instock', 'onbackorder']).count()
        sas_products = SASProduct.objects.filter(stock_status__in=['instock', 'onbackorder']).count()
        context['total_products'] = lotto_products + sas_products

        return context


def frontend_landing_view(request):
    """Serve the frontend landing page with featured clubs only"""
    from django.db.models import Q

    # Get 3 LOTTO clubs (exclude product/apparel names)
    lotto_clubs = LottoClub.objects.filter(
        is_active=True,
        logo__isnull=False
    ).exclude(
        logo=''
    ).exclude(
        Q(name__icontains='APPAREL') |
        Q(name__icontains='GARMENT') |
        Q(name__icontains='UNIFORM') |
        Q(name__icontains='CLOTHING') |
        Q(name__icontains='PRODUCT') |
        Q(name__icontains='REFEREE')
    ).order_by('?')[:3]  # Random 3 clubs

    # Get 3 SAS clubs from SASClub model
    sas_clubs = SASClub.objects.filter(
        is_active=True,
        image_url__isnull=False
    ).exclude(
        image_url=''
    ).order_by('?')[:3]  # Random 3 clubs

    context = {
        'lotto_clubs': lotto_clubs,
        'sas_clubs': sas_clubs,
    }

    return render(request, 'frontend/home.html', context)


def products_view(request):
    """Serve the products listing page"""
    return render(request, 'frontend/products.html')


def get_random_clubs_ajax(request):
    """AJAX endpoint to get random clubs for rotation"""
    from django.http import JsonResponse
    from django.db.models import Q

    # Get 3 random LOTTO clubs (exclude product/apparel names)
    lotto_clubs = list(LottoClub.objects.filter(
        is_active=True,
        logo__isnull=False
    ).exclude(
        logo=''
    ).exclude(
        Q(name__icontains='APPAREL') |
        Q(name__icontains='GARMENT') |
        Q(name__icontains='UNIFORM') |
        Q(name__icontains='CLOTHING') |
        Q(name__icontains='PRODUCT') |
        Q(name__icontains='REFEREE')
    ).order_by('?')[:3].values('name', 'logo'))

    # Rename logo field to logo_url for consistency
    for club in lotto_clubs:
        club['logo_url'] = club.pop('logo')

    # Get 3 random SAS clubs
    sas_clubs = list(SASClub.objects.filter(
        is_active=True,
        image_url__isnull=False
    ).exclude(
        image_url=''
    ).order_by('?')[:3].values('name', 'image_url'))

    # Rename image_url to logo_url for consistency
    for club in sas_clubs:
        club['logo_url'] = club.pop('image_url')

    return JsonResponse({
        'success': True,
        'lotto_clubs': lotto_clubs,
        'sas_clubs': sas_clubs
    })


def product_detail_view(request):
    """Serve the product detail page"""
    return render(request, 'frontend/product-detail.html')


def cart_view(request):
    """Serve the shopping cart page"""
    return render(request, 'frontend/cart.html')


def user_choice_view(request):
    """Serve the original user choice page (School/Club Admin vs Customer)"""
    return render(request, 'frontend/index.html')