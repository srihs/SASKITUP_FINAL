from django.shortcuts import render
from django.views.generic import TemplateView
from clubs.models import Club, ClubCategory, Product


class GlobalDashboardView(TemplateView):
    """Main global dashboard for the SASKITUP admin system"""
    template_name = 'dashboard/global_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Basic statistics for the dashboard
        context['total_clubs'] = Club.objects.filter(is_active=True).count()
        context['total_lotto_clubs'] = Club.objects.filter(is_active=True, club_type='LOTTO').count()
        context['total_sas_clubs'] = Club.objects.filter(is_active=True, club_type='SAS').count()
        context['total_categories'] = ClubCategory.objects.filter(product_count__gt=0).count()
        context['total_products'] = Product.objects.filter(stock_status__in=['instock', 'onbackorder']).count()
        
        return context