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
    """Serve the frontend landing page with featured schools and clubs"""
    # Get 6 retail schools with logos from TUS
    retail_schools = TUSSchool.objects.filter(
        is_active=True,
        logo_url__isnull=False
    ).exclude(
        logo_url=''
    )[:6]

    # Get 3 LOTTO clubs from LottoClub model
    lotto_clubs = LottoClub.objects.filter(
        is_active=True,
        logo__isnull=False
    ).exclude(
        logo=''
    )[:3]

    # Get 3 SAS clubs from SASClub model
    sas_clubs = SASClub.objects.filter(
        is_active=True,
        image_url__isnull=False
    ).exclude(
        image_url=''
    )[:3]

    context = {
        'retail_schools': retail_schools,
        'lotto_clubs': lotto_clubs,
        'sas_clubs': sas_clubs,
    }

    return render(request, 'frontend/home.html', context)


def products_view(request):
    """Serve the products listing page"""
    return render(request, 'frontend/products.html')


def product_detail_view(request):
    """Serve the product detail page"""
    return render(request, 'frontend/product-detail.html')


def cart_view(request):
    """Serve the shopping cart page"""
    return render(request, 'frontend/cart.html')


def user_choice_view(request):
    """Serve the original user choice page (School/Club Admin vs Customer)"""
    return render(request, 'frontend/index.html')