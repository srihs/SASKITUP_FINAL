from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.urls import reverse_lazy, reverse
from django.db.models import Q, Count
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.forms import ModelForm
from django import forms

from .models import (
    User, SalesRepSchoolAssignment, SalesRepClubAssignment, AuditLog
)
from .permissions import (
    AdminRequiredMixin, AssignmentPermissionMixin,
    can_user_manage_assignments
)
from clubs.models import Club
from schools.models import School, WholesaleSchool


class AssignmentForm(ModelForm):
    """Base form for assignments"""
    class Meta:
        fields = [
            'sales_rep', 'is_active', 'territory_name',
            'priority_level', 'notes'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit sales_rep choices to active sales representatives
        self.fields['sales_rep'].queryset = User.objects.filter(
            user_type='sales_rep',
            is_active=True,
            is_active_sales_rep=True
        )


class SchoolAssignmentForm(AssignmentForm):
    """Form for school assignments"""
    class Meta(AssignmentForm.Meta):
        model = SalesRepSchoolAssignment
        fields = AssignmentForm.Meta.fields + ['school', 'wholesale_school']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add help text
        self.fields['school'].help_text = "Select a regular school (leave blank if assigning wholesale school)"
        self.fields['wholesale_school'].help_text = "Select a wholesale school (leave blank if assigning regular school)"

    def clean(self):
        cleaned_data = super().clean()
        school = cleaned_data.get('school')
        wholesale_school = cleaned_data.get('wholesale_school')

        if school and wholesale_school:
            raise forms.ValidationError(
                "Please select either a regular school or wholesale school, not both."
            )

        if not school and not wholesale_school:
            raise forms.ValidationError(
                "Please select either a regular school or wholesale school."
            )

        return cleaned_data


class ClubAssignmentForm(AssignmentForm):
    """Form for club assignments"""
    class Meta(AssignmentForm.Meta):
        model = SalesRepClubAssignment
        fields = AssignmentForm.Meta.fields + ['club']


class SchoolAssignmentListView(AdminRequiredMixin, ListView):
    """List school assignments"""
    model = SalesRepSchoolAssignment
    template_name = 'authentication/school_assignment_list.html'
    context_object_name = 'assignments'
    paginate_by = 20

    def get_queryset(self):
        queryset = SalesRepSchoolAssignment.objects.select_related(
            'sales_rep', 'school', 'wholesale_school'
        ).order_by('-assigned_date')

        # Filter by sales rep
        sales_rep = self.request.GET.get('sales_rep')
        if sales_rep:
            queryset = queryset.filter(sales_rep_id=sales_rep)

        # Filter by active status
        is_active = self.request.GET.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active == 'true')

        # Filter by school type
        school_type = self.request.GET.get('school_type')
        if school_type == 'regular':
            queryset = queryset.filter(school__isnull=False)
        elif school_type == 'wholesale':
            queryset = queryset.filter(wholesale_school__isnull=False)

        # Search by school name
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(school__org_name__icontains=search) |
                Q(wholesale_school__name__icontains=search) |
                Q(sales_rep__first_name__icontains=search) |
                Q(sales_rep__last_name__icontains=search) |
                Q(territory_name__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sales_reps'] = User.objects.filter(user_type='sales_rep').order_by('first_name', 'last_name')
        context['current_filters'] = {
            'sales_rep': self.request.GET.get('sales_rep', ''),
            'is_active': self.request.GET.get('is_active', ''),
            'school_type': self.request.GET.get('school_type', ''),
            'search': self.request.GET.get('search', ''),
        }

        # Statistics
        context['total_assignments'] = self.get_queryset().count()
        context['active_assignments'] = self.get_queryset().filter(is_active=True).count()

        return context


class SchoolAssignmentDetailView(AdminRequiredMixin, DetailView):
    """View school assignment details"""
    model = SalesRepSchoolAssignment
    template_name = 'authentication/school_assignment_detail.html'
    context_object_name = 'assignment'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get assignment history for this school
        assignment = self.object
        if assignment.school:
            context['assignment_history'] = SalesRepSchoolAssignment.objects.filter(
                school=assignment.school
            ).exclude(pk=assignment.pk).order_by('-assigned_date')
        elif assignment.wholesale_school:
            context['assignment_history'] = SalesRepSchoolAssignment.objects.filter(
                wholesale_school=assignment.wholesale_school
            ).exclude(pk=assignment.pk).order_by('-assigned_date')

        return context


class SchoolAssignmentCreateView(AdminRequiredMixin, CreateView):
    """Create school assignment"""
    model = SalesRepSchoolAssignment
    form_class = SchoolAssignmentForm
    template_name = 'authentication/school_assignment_form.html'
    success_url = reverse_lazy('authentication:school-assignment-list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        # Log assignment creation
        school_name = form.instance.school_name
        AuditLog.log_action(
            user=self.request.user,
            action_type='assignment_created',
            description=f'Assigned {form.instance.sales_rep.get_full_name()} to school: {school_name}',
            request=self.request,
            assignment_id=str(self.object.id),
            sales_rep_id=form.instance.sales_rep.id,
            school_name=school_name
        )

        messages.success(self.request, f'School assignment created successfully.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Create School Assignment'
        context['submit_text'] = 'Create Assignment'
        return context


class SchoolAssignmentUpdateView(AdminRequiredMixin, UpdateView):
    """Update school assignment"""
    model = SalesRepSchoolAssignment
    form_class = SchoolAssignmentForm
    template_name = 'authentication/school_assignment_form.html'

    def get_success_url(self):
        return reverse('authentication:school-assignment-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)

        # Log assignment update
        school_name = form.instance.school_name
        AuditLog.log_action(
            user=self.request.user,
            action_type='assignment_updated',
            description=f'Updated school assignment: {form.instance.sales_rep.get_full_name()} → {school_name}',
            request=self.request,
            assignment_id=str(self.object.id),
            sales_rep_id=form.instance.sales_rep.id,
            school_name=school_name
        )

        messages.success(self.request, f'School assignment updated successfully.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Update School Assignment'
        context['submit_text'] = 'Update Assignment'
        return context


class ClubAssignmentListView(AdminRequiredMixin, ListView):
    """List club assignments"""
    model = SalesRepClubAssignment
    template_name = 'authentication/club_assignment_list.html'
    context_object_name = 'assignments'
    paginate_by = 20

    def get_queryset(self):
        queryset = SalesRepClubAssignment.objects.select_related(
            'sales_rep', 'club'
        ).order_by('-assigned_date')

        # Filter by sales rep
        sales_rep = self.request.GET.get('sales_rep')
        if sales_rep:
            queryset = queryset.filter(sales_rep_id=sales_rep)

        # Filter by active status
        is_active = self.request.GET.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active == 'true')

        # Filter by club type
        club_type = self.request.GET.get('club_type')
        if club_type:
            queryset = queryset.filter(club__club_type=club_type)

        # Search by club name
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(club__name__icontains=search) |
                Q(sales_rep__first_name__icontains=search) |
                Q(sales_rep__last_name__icontains=search) |
                Q(territory_name__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sales_reps'] = User.objects.filter(user_type='sales_rep').order_by('first_name', 'last_name')
        context['club_types'] = Club.CLUB_TYPES
        context['current_filters'] = {
            'sales_rep': self.request.GET.get('sales_rep', ''),
            'is_active': self.request.GET.get('is_active', ''),
            'club_type': self.request.GET.get('club_type', ''),
            'search': self.request.GET.get('search', ''),
        }

        # Statistics
        context['total_assignments'] = self.get_queryset().count()
        context['active_assignments'] = self.get_queryset().filter(is_active=True).count()

        return context


class ClubAssignmentDetailView(AdminRequiredMixin, DetailView):
    """View club assignment details"""
    model = SalesRepClubAssignment
    template_name = 'authentication/club_assignment_detail.html'
    context_object_name = 'assignment'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get assignment history for this club
        assignment = self.object
        context['assignment_history'] = SalesRepClubAssignment.objects.filter(
            club=assignment.club
        ).exclude(pk=assignment.pk).order_by('-assigned_date')

        return context


class ClubAssignmentCreateView(AdminRequiredMixin, CreateView):
    """Create club assignment"""
    model = SalesRepClubAssignment
    form_class = ClubAssignmentForm
    template_name = 'authentication/club_assignment_form.html'
    success_url = reverse_lazy('authentication:club-assignment-list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        # Log assignment creation
        AuditLog.log_action(
            user=self.request.user,
            action_type='assignment_created',
            description=f'Assigned {form.instance.sales_rep.get_full_name()} to club: {form.instance.club.name}',
            request=self.request,
            assignment_id=str(self.object.id),
            sales_rep_id=form.instance.sales_rep.id,
            club_id=form.instance.club.id
        )

        messages.success(self.request, f'Club assignment created successfully.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Create Club Assignment'
        context['submit_text'] = 'Create Assignment'
        return context


class ClubAssignmentUpdateView(AdminRequiredMixin, UpdateView):
    """Update club assignment"""
    model = SalesRepClubAssignment
    form_class = ClubAssignmentForm
    template_name = 'authentication/club_assignment_form.html'

    def get_success_url(self):
        return reverse('authentication:club-assignment-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)

        # Log assignment update
        AuditLog.log_action(
            user=self.request.user,
            action_type='assignment_updated',
            description=f'Updated club assignment: {form.instance.sales_rep.get_full_name()} → {form.instance.club.name}',
            request=self.request,
            assignment_id=str(self.object.id),
            sales_rep_id=form.instance.sales_rep.id,
            club_id=form.instance.club.id
        )

        messages.success(self.request, f'Club assignment updated successfully.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Update Club Assignment'
        context['submit_text'] = 'Update Assignment'
        return context


class AuditLogListView(AdminRequiredMixin, ListView):
    """List audit logs"""
    model = AuditLog
    template_name = 'authentication/audit_log_list.html'
    context_object_name = 'audit_logs'
    paginate_by = 50

    def get_queryset(self):
        queryset = AuditLog.objects.select_related('user').order_by('-timestamp')

        # Filter by user
        user_id = self.request.GET.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by action type
        action_type = self.request.GET.get('action_type')
        if action_type:
            queryset = queryset.filter(action_type=action_type)

        # Date range filter
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
        context['action_types'] = AuditLog.ACTION_TYPES
        context['current_filters'] = {
            'user': self.request.GET.get('user', ''),
            'action_type': self.request.GET.get('action_type', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        return context


# AJAX Views for assignments

@login_required
def school_search_ajax(request):
    """AJAX search for schools"""
    if not can_user_manage_assignments(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    query = request.GET.get('q', '')
    school_type = request.GET.get('type', 'regular')  # 'regular' or 'wholesale'

    if len(query) < 2:
        return JsonResponse({'results': []})

    results = []

    if school_type == 'regular':
        schools = School.objects.filter(
            org_name__icontains=query
        )[:10]

        for school in schools:
            # Check if already assigned
            is_assigned = SalesRepSchoolAssignment.objects.filter(
                school=school,
                is_active=True
            ).exists()

            results.append({
                'id': school.id,
                'text': school.org_name,
                'type': 'regular',
                'is_assigned': is_assigned,
                'assigned_to': school.sales_rep_assignments.filter(is_active=True).first().sales_rep.get_full_name() if is_assigned else None
            })

    elif school_type == 'wholesale':
        schools = WholesaleSchool.objects.filter(
            name__icontains=query,
            is_active=True
        )[:10]

        for school in schools:
            # Check if already assigned
            is_assigned = SalesRepSchoolAssignment.objects.filter(
                wholesale_school=school,
                is_active=True
            ).exists()

            results.append({
                'id': school.id,
                'text': school.name,
                'type': 'wholesale',
                'is_assigned': is_assigned,
                'assigned_to': school.sales_rep_assignments.filter(is_active=True).first().sales_rep.get_full_name() if is_assigned else None
            })

    return JsonResponse({'results': results})


@login_required
def club_search_ajax(request):
    """AJAX search for clubs"""
    if not can_user_manage_assignments(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})

    clubs = Club.objects.filter(
        name__icontains=query,
        is_active=True
    )[:10]

    results = []
    for club in clubs:
        # Check if already assigned
        is_assigned = SalesRepClubAssignment.objects.filter(
            club=club,
            is_active=True
        ).exists()

        results.append({
            'id': club.id,
            'text': f"{club.name} ({club.get_club_type_display()})",
            'club_type': club.club_type,
            'is_assigned': is_assigned,
            'assigned_to': club.sales_rep_assignments.filter(is_active=True).first().sales_rep.get_full_name() if is_assigned else None
        })

    return JsonResponse({'results': results})


@login_required
def assignment_stats_ajax(request):
    """AJAX endpoint for assignment statistics"""
    if not can_user_manage_assignments(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # School assignment stats
    school_stats = {
        'total': SalesRepSchoolAssignment.objects.count(),
        'active': SalesRepSchoolAssignment.objects.filter(is_active=True).count(),
        'regular_schools': SalesRepSchoolAssignment.objects.filter(
            school__isnull=False, is_active=True
        ).count(),
        'wholesale_schools': SalesRepSchoolAssignment.objects.filter(
            wholesale_school__isnull=False, is_active=True
        ).count(),
    }

    # Club assignment stats
    club_stats = {
        'total': SalesRepClubAssignment.objects.count(),
        'active': SalesRepClubAssignment.objects.filter(is_active=True).count(),
        'lotto_clubs': SalesRepClubAssignment.objects.filter(
            club__club_type='LOTTO', is_active=True
        ).count(),
        'sas_clubs': SalesRepClubAssignment.objects.filter(
            club__club_type='SAS', is_active=True
        ).count(),
    }

    # Sales rep stats
    sales_rep_stats = User.objects.filter(
        user_type='sales_rep',
        is_active=True
    ).annotate(
        school_count=Count('school_assignments', filter=Q(school_assignments__is_active=True)),
        club_count=Count('club_assignments', filter=Q(club_assignments__is_active=True))
    )

    top_sales_reps = []
    for rep in sales_rep_stats.order_by('-school_count', '-club_count')[:5]:
        top_sales_reps.append({
            'name': rep.get_full_name() or rep.username,
            'schools': rep.school_count,
            'clubs': rep.club_count,
            'total': rep.school_count + rep.club_count
        })

    return JsonResponse({
        'school_stats': school_stats,
        'club_stats': club_stats,
        'top_sales_reps': top_sales_reps
    })


class AssignmentManagementView(AdminRequiredMixin, ListView):
    """Enhanced Assignment Management Interface"""
    template_name = 'authentication/assignment_management.html'
    context_object_name = 'sales_reps'
    paginate_by = 20

    def get_queryset(self):
        return User.objects.filter(
            user_type='sales_rep',
            is_active=True
        ).prefetch_related(
            'school_assignments',
            'club_assignments'
        ).order_by('first_name', 'last_name', 'username')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Assignment statistics
        context['stats'] = {
            'total_assignments': SalesRepSchoolAssignment.objects.filter(is_active=True).count() +
                               SalesRepClubAssignment.objects.filter(is_active=True).count(),
            'unassigned_schools': School.objects.filter(
                sales_rep_assignments__isnull=True
            ).count() + WholesaleSchool.objects.filter(
                sales_rep_assignments__isnull=True
            ).count(),
            'unassigned_clubs': Club.objects.filter(
                sales_rep_assignments__isnull=True
            ).count(),
            'active_sales_reps': User.objects.filter(
                user_type='sales_rep',
                is_active=True,
                is_active_sales_rep=True
            ).count(),
        }

        return context


class AuditLogListView(AdminRequiredMixin, ListView):
    """Enhanced Audit Log Viewer"""
    model = AuditLog
    template_name = 'authentication/audit_log_list.html'
    context_object_name = 'audit_logs'
    paginate_by = 50

    def get_queryset(self):
        queryset = AuditLog.objects.select_related('user').order_by('-timestamp')

        # Filter by action type
        action_type = self.request.GET.get('action_type')
        if action_type:
            queryset = queryset.filter(action_type=action_type)

        # Filter by user
        user_filter = self.request.GET.get('user_filter')
        if user_filter:
            queryset = queryset.filter(user_id=user_filter)

        # Filter by date range
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)

        # Search in description
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(description__icontains=search)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Users for filter dropdown
        context['users'] = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')

        # Audit statistics
        from django.utils import timezone
        today = timezone.now().date()

        context['audit_stats'] = {
            'total_events': AuditLog.objects.count(),
            'today_events': AuditLog.objects.filter(timestamp__date=today).count(),
            'unique_users': AuditLog.objects.filter(user__isnull=False).values('user').distinct().count(),
            'critical_events': AuditLog.objects.filter(
                action_type__in=['admin_action', 'user_deactivated', 'assignment_deleted']
            ).filter(timestamp__date=today).count(),
        }

        return context