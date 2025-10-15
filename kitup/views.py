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
from schools.models_tus import TUSSchool


class GlobalDashboardView(LoginRequiredMixin, TemplateView):
    """
    Unified dashboard for all user roles.
    Content and stats filtered based on user.user_type:
    - Admins: See ALL system data
    - Account Managers: See ALL schools/clubs, own quotations
    - Sales Reps: See ONLY assigned schools/clubs, own quotations
    - Customers: See ONLY own data
    """
    template_name = 'dashboard/global_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Add user info to context
        context['user_role'] = user.get_user_type_display()
        context['user_full_name'] = user.get_full_name() or user.username

        # Get role-specific stats and data
        if user.is_admin:
            context.update(self._get_admin_context())
        elif user.is_account_manager:
            context.update(self._get_account_manager_context(user))
        elif user.is_sales_rep:
            context.update(self._get_sales_rep_context(user))
        elif user.is_customer:
            context.update(self._get_customer_context(user))

        return context

    def _get_admin_context(self):
        """Admin sees ALL system data"""
        from schools.models import WholesaleSchool
        from authentication.models import User

        # Try to import Quotation model, handle if not available
        try:
            from quotations.models import Quotation
            has_quotations = True
        except ImportError:
            has_quotations = False

        context = {
            # Schools
            'total_tus_schools': TUSSchool.objects.filter(is_active=True).count(),
            'total_wholesale_schools': WholesaleSchool.objects.filter(is_active=True).count(),

            # Clubs
            'total_lotto_clubs': LottoClub.objects.filter(is_active=True).count(),
            'total_sas_clubs': SASClub.objects.filter(is_active=True).count(),

            # Users
            'total_users': User.objects.filter(is_active=True).count(),
            'total_sales_reps': User.objects.filter(user_type='sales_rep', is_active=True).count(),
            'total_account_managers': User.objects.filter(user_type='account_manager', is_active=True).count(),
            'total_customers': User.objects.filter(user_type='customer', is_active=True).count(),
        }

        # Calculate totals
        context['total_schools'] = context['total_tus_schools'] + context['total_wholesale_schools']
        context['total_clubs'] = context['total_lotto_clubs'] + context['total_sas_clubs']

        # Add quotation stats if available
        if has_quotations:
            context.update({
                'total_quotations': Quotation.objects.count(),
                'pending_quotations': Quotation.objects.filter(status='pending').count(),
                'approved_quotations': Quotation.objects.filter(status='approved').count(),
                'draft_quotations': Quotation.objects.filter(status='draft').count(),
                'recent_quotations': Quotation.objects.select_related('created_by').order_by('-created_at')[:5],
            })
        else:
            context.update({
                'total_quotations': 0,
                'pending_quotations': 0,
                'approved_quotations': 0,
                'draft_quotations': 0,
                'recent_quotations': [],
            })

        return context

    def _get_account_manager_context(self, user):
        """Account Managers see ALL schools and clubs (same as admin for clients)"""
        from schools.models import WholesaleSchool

        # Try to import Quotation model
        try:
            from quotations.models import Quotation
            has_quotations = True
        except ImportError:
            has_quotations = False

        context = {
            # Schools (ALL - Account Manager Access)
            'total_tus_schools': TUSSchool.objects.filter(is_active=True).count(),
            'total_wholesale_schools': WholesaleSchool.objects.filter(is_active=True).count(),

            # Clubs (ALL)
            'total_lotto_clubs': LottoClub.objects.filter(is_active=True).count(),
            'total_sas_clubs': SASClub.objects.filter(is_active=True).count(),
        }

        # Calculate totals
        context['total_schools'] = context['total_tus_schools'] + context['total_wholesale_schools']
        context['total_clubs'] = context['total_lotto_clubs'] + context['total_sas_clubs']

        # Add quotation stats (own only)
        if has_quotations:
            context.update({
                'my_quotations': Quotation.objects.filter(created_by=user).count(),
                'my_pending_quotations': Quotation.objects.filter(created_by=user, status='pending').count(),
                'my_approved_quotations': Quotation.objects.filter(created_by=user, status='approved').count(),
                'my_draft_quotations': Quotation.objects.filter(created_by=user, status='draft').count(),
                'recent_quotations': Quotation.objects.filter(created_by=user).order_by('-created_at')[:5],
            })
        else:
            context.update({
                'my_quotations': 0,
                'my_pending_quotations': 0,
                'my_approved_quotations': 0,
                'my_draft_quotations': 0,
                'recent_quotations': [],
            })

        return context

    def _get_sales_rep_context(self, user):
        """Sales Reps see ONLY assigned schools and clubs"""
        from authentication.models import SalesRepSchoolAssignment, SalesRepClubAssignment
        from django.contrib.contenttypes.models import ContentType

        # Try to import Quotation model
        try:
            from quotations.models import Quotation
            has_quotations = True
        except ImportError:
            has_quotations = False

        # Get assignments
        school_assignments = SalesRepSchoolAssignment.objects.filter(
            sales_rep=user,
            is_active=True
        ).select_related('tus_school', 'wholesale_school')

        club_assignments = SalesRepClubAssignment.objects.filter(
            sales_rep=user,
            is_active=True
        ).select_related('club_content_type')

        # Count by type
        tus_count = school_assignments.filter(tus_school__isnull=False).count()
        wholesale_count = school_assignments.filter(wholesale_school__isnull=False).count()

        lotto_ct = ContentType.objects.get_for_model(LottoClub)
        sas_ct = ContentType.objects.get_for_model(SASClub)

        lotto_count = club_assignments.filter(club_content_type=lotto_ct).count()
        sas_count = club_assignments.filter(club_content_type=sas_ct).count()

        context = {
            # Assigned Schools
            'my_tus_schools': tus_count,
            'my_wholesale_schools': wholesale_count,
            'my_schools': school_assignments.count(),

            # Assigned Clubs
            'my_lotto_clubs': lotto_count,
            'my_sas_clubs': sas_count,
            'my_clubs': club_assignments.count(),

            # Detailed assignments for display
            'assigned_schools': school_assignments[:10],  # Limit for dashboard
            'assigned_clubs': club_assignments[:10],
        }

        # Add quotation stats (own only)
        if has_quotations:
            context.update({
                'my_quotations': Quotation.objects.filter(created_by=user).count(),
                'my_pending_quotations': Quotation.objects.filter(created_by=user, status='pending').count(),
                'my_approved_quotations': Quotation.objects.filter(created_by=user, status='approved').count(),
                'my_draft_quotations': Quotation.objects.filter(created_by=user, status='draft').count(),
                'recent_quotations': Quotation.objects.filter(created_by=user).order_by('-created_at')[:5],
            })
        else:
            context.update({
                'my_quotations': 0,
                'my_pending_quotations': 0,
                'my_approved_quotations': 0,
                'my_draft_quotations': 0,
                'recent_quotations': [],
            })

        return context

    def _get_customer_context(self, user):
        """Customers see ONLY their own data"""
        # Try to import Quotation model
        try:
            from quotations.models import Quotation
            has_quotations = True
        except ImportError:
            has_quotations = False

        context = {
            # Placeholder for future customer features
            'my_orders': 0,
            'pending_orders': 0,
        }

        # Add quotation stats (own only)
        if has_quotations:
            context.update({
                'my_quotations': Quotation.objects.filter(created_by=user).count(),
                'my_pending_quotations': Quotation.objects.filter(created_by=user, status='pending').count(),
                'my_approved_quotations': Quotation.objects.filter(created_by=user, status='approved').count(),
                'my_draft_quotations': Quotation.objects.filter(created_by=user, status='draft').count(),
                'recent_quotations': Quotation.objects.filter(created_by=user).order_by('-created_at')[:5],
            })
        else:
            context.update({
                'my_quotations': 0,
                'my_pending_quotations': 0,
                'my_approved_quotations': 0,
                'my_draft_quotations': 0,
                'recent_quotations': [],
            })

        return context


def frontend_landing_view(request):
    """
    Index page with unified dashboard redirection and login handling
    - All authenticated users → /dashboard/ (with role-based content)
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
            # All users now redirect to unified dashboard
            return redirect('global-dashboard')
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

    # If user is authenticated, redirect to unified dashboard
    if request.user.is_authenticated:
        # All authenticated users redirect to unified dashboard
        return redirect('global-dashboard')

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

    return render(request, 'home.html', context)


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
        from schools.models_tus import TUSSchool
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