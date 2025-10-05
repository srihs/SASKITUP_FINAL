from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.generic import TemplateView
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from clubs.models_lotto import LottoClub, LottoClubCategory, LottoProduct
from clubs.models_sas import SASClub, SASProduct
from clubs.models_tus import TUSSchool


@method_decorator(login_required, name='dispatch')
class GlobalDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Main global dashboard for the SASKITUP admin system"""
    template_name = 'dashboard/global_dashboard.html'
    login_url = '/'

    def test_func(self):
        """Only allow admin and superuser access"""
        return self.request.user.user_type in ['admin'] or self.request.user.is_superuser

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
    """
    Index page with role-based redirection and login handling
    - Admin/Superadmin → /dashboard/
    - Sales Rep/Account Manager → /profile/
    - Customer → /profile/
    - Not authenticated → landing page with login form
    - POST: Process login
    """
    from django.db.models import Q
    from authentication.models import AuditLog

    # Handle login POST request
    if request.method == 'POST' and not request.user.is_authenticated:
        username = request.POST.get('username')  # Email field
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Log successful login
            AuditLog.log_action(
                user=user,
                action_type='login',
                description=f'User {user.username} logged in successfully from home page',
                request=request
            )

            # Role-based redirection after successful login
            if user.user_type in ['admin'] or user.is_superuser:
                return redirect('global-dashboard')
            else:
                # Sales reps, account managers, and customers → Profile
                return redirect('profile')
        else:
            # Log failed login attempt
            AuditLog.log_action(
                user=None,
                action_type='login',
                description=f'Failed login attempt for email: {username}',
                request=request,
                email=username
            )
            messages.error(request, 'Invalid email or password.')
            # Continue to show the home page with error message

    # If user is authenticated, redirect based on role
    if request.user.is_authenticated:
        user = request.user

        # Admin and Superadmin users → Global Dashboard
        if user.user_type in ['admin'] or user.is_superuser:
            return redirect('global-dashboard')

        # Sales Reps, Account Managers, and Customers → Profile
        else:
            return redirect('profile')

    # Not authenticated → Show landing page with login form
    # Get ALL retail schools (TUS) with logos
    retail_schools = TUSSchool.objects.filter(
        is_active=True,
        logo_url__isnull=False
    ).exclude(
        logo_url=''
    ).order_by('name')  # All schools, alphabetically

    # Get ALL LOTTO clubs (exclude product/apparel names)
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
    ).order_by('name')  # All clubs, alphabetically

    # Get ALL SAS clubs from SASClub model
    sas_clubs = SASClub.objects.filter(
        is_active=True,
        image_url__isnull=False
    ).exclude(
        image_url=''
    ).order_by('name')  # All clubs, alphabetically

    context = {
        'retail_schools': retail_schools,
        'lotto_clubs': lotto_clubs,
        'sas_clubs': sas_clubs,
    }

    return render(request, 'frontend/home.html', context)


def products_view(request):
    """Serve the products listing page"""
    return render(request, 'frontend/products.html')


def get_random_clubs_ajax(request):
    """AJAX endpoint to get all schools and clubs"""
    from django.http import JsonResponse
    from django.db.models import Q

    # Get ALL retail schools (TUS)
    retail_schools = list(TUSSchool.objects.filter(
        is_active=True,
        logo_url__isnull=False
    ).exclude(
        logo_url=''
    ).order_by('name').values('name', 'logo_url'))

    # Get ALL LOTTO clubs (exclude product/apparel names)
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
    ).order_by('name').values('name', 'logo'))

    # Rename logo field to logo_url for consistency
    for club in lotto_clubs:
        club['logo_url'] = club.pop('logo')

    # Get ALL SAS clubs
    sas_clubs = list(SASClub.objects.filter(
        is_active=True,
        image_url__isnull=False
    ).exclude(
        image_url=''
    ).order_by('name').values('name', 'image_url'))

    # Rename image_url to logo_url for consistency
    for club in sas_clubs:
        club['logo_url'] = club.pop('image_url')

    return JsonResponse({
        'success': True,
        'retail_schools': retail_schools,
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


class ProfileView(TemplateView):
    """
    Frontend profile view for sales reps, account managers, and customers
    - Sales Reps/Account Managers → profile_sales.html
    - Customers → profile_customer.html
    """

    def dispatch(self, request, *args, **kwargs):
        """Check authentication and redirect to home if not authenticated"""
        if not request.user.is_authenticated:
            return redirect('frontend-home')
        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        """Return appropriate template based on user type"""
        user = self.request.user

        if user.user_type in ['sales_rep', 'account_manager']:
            return ['frontend/profile_sales.html']
        elif user.user_type == 'customer':
            return ['frontend/profile_customer.html']
        else:
            # Fallback for other user types (shouldn't happen)
            return redirect('global-dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Common context for all profiles
        context['user_obj'] = user

        # Import models needed for context
        from authentication.models import AuditLog, SalesRepSchoolAssignment, SalesRepClubAssignment
        from clubs.models_lotto import LottoClub
        from clubs.models_sas import SASClub
        from clubs.models_tus import TUSSchool
        from schools.models import WholesaleSchool
        from django.contrib.contenttypes.models import ContentType

        # Get recent activities
        context['recent_activities'] = AuditLog.objects.filter(
            user=user
        ).order_by('-timestamp')[:20]

        # Sales Rep/Account Manager specific context
        if user.user_type in ['sales_rep', 'account_manager']:
            # Get assigned TUS schools
            tus_assignments = SalesRepSchoolAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                tus_school_id__isnull=False
            ).select_related('sales_rep', 'tus_school')

            tus_schools = []
            for assignment in tus_assignments:
                if assignment.tus_school and assignment.tus_school.is_active:
                    tus_schools.append({
                        'school': assignment.tus_school,
                        'assignment': assignment,
                        'type': 'TUS School'
                    })

            # Get assigned wholesale schools
            wholesale_assignments = SalesRepSchoolAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                wholesale_school__isnull=False
            ).select_related('sales_rep', 'wholesale_school')

            wholesale_schools = [
                {
                    'school': assignment.wholesale_school,
                    'assignment': assignment,
                    'type': 'Wholesale School'
                }
                for assignment in wholesale_assignments
            ]

            # Get assigned LOTTO clubs
            lotto_content_type = ContentType.objects.get_for_model(LottoClub)
            lotto_assignments = SalesRepClubAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                club_content_type=lotto_content_type
            ).select_related('sales_rep', 'club_content_type')

            lotto_clubs = []
            for assignment in lotto_assignments:
                try:
                    club = LottoClub.objects.get(id=assignment.club_object_id, is_active=True)
                    lotto_clubs.append({
                        'club': club,
                        'assignment': assignment,
                        'type': 'LOTTO Club'
                    })
                except LottoClub.DoesNotExist:
                    continue

            # Get assigned SAS clubs
            sas_content_type = ContentType.objects.get_for_model(SASClub)
            sas_assignments = SalesRepClubAssignment.objects.filter(
                sales_rep=user,
                is_active=True,
                club_content_type=sas_content_type
            ).select_related('sales_rep', 'club_content_type')

            sas_clubs = []
            for assignment in sas_assignments:
                try:
                    club = SASClub.objects.get(id=assignment.club_object_id, is_active=True)
                    sas_clubs.append({
                        'club': club,
                        'assignment': assignment,
                        'type': 'SAS Club'
                    })
                except SASClub.DoesNotExist:
                    continue

            context.update({
                'tus_schools': tus_schools,
                'wholesale_schools': wholesale_schools,
                'lotto_clubs': lotto_clubs,
                'sas_clubs': sas_clubs,
                'total_assignments': len(tus_schools) + len(wholesale_schools) + len(lotto_clubs) + len(sas_clubs),
                # Placeholder for quotations - will be implemented in Phase 2
                'quotations': [],
            })

        # Customer specific context
        elif user.user_type == 'customer':
            context.update({
                'organization': None,  # Placeholder - will link to TUSSchool, WholesaleSchool, or Club
                'assigned_sales_rep': None,  # Placeholder - will get from assignments
                # Placeholder for quotations - will be implemented in Phase 2
                'quotations': [],
            })

        return context