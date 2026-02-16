from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from datetime import date
from .models import Store, StorePeriod, StoreOpeningHours
from .forms import StoreForm, StorePeriodAssignmentForm


def is_superuser(user):
    """Check if user is superuser."""
    return user.is_superuser


class SuperuserRequiredMixin(UserPassesTestMixin):
    """Mixin to require superuser access."""
    def test_func(self):
        return self.request.user.is_superuser


class StoreListView(LoginRequiredMixin, ListView):
    """View for displaying all stores (active only for non-superusers)."""
    model = Store
    template_name = 'stores/store_list.html'
    context_object_name = 'stores'

    def get_queryset(self):
        """Return stores based on user permissions."""
        if self.request.user.is_superuser:
            # Superusers see all stores
            return Store.objects.all().prefetch_related('schools', 'opening_hours')
        else:
            # Regular users see only active stores
            return Store.objects.filter(is_active=True).prefetch_related('schools', 'opening_hours')


class OpeningHoursManagementView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
    """View for managing opening hours across all stores."""
    model = Store
    template_name = 'stores/opening_hours_management.html'
    context_object_name = 'stores'

    def get_queryset(self):
        """Return all stores with their periods."""
        return Store.objects.all().prefetch_related('periods', 'opening_hours').order_by('display_order', 'name')

    def get_context_data(self, **kwargs):
        """Add period statistics for each store."""
        context = super().get_context_data(**kwargs)
        today = date.today()

        # Add period info for each store
        for store in context['stores']:
            store.active_period = store.get_current_period()
            store.total_periods = store.periods.count()
            store.active_periods_count = store.periods.filter(
                is_active=True,
                start_date__lte=today,
                end_date__gte=today
            ).count()

        return context


class StoreDetailView(LoginRequiredMixin, DetailView):
    """View for displaying a single store with all details."""
    model = Store
    template_name = 'stores/store_detail.html'
    context_object_name = 'store'

    def get_queryset(self):
        """Return stores based on user permissions."""
        if self.request.user.is_superuser:
            return Store.objects.all().prefetch_related('schools', 'opening_hours')
        else:
            return Store.objects.filter(is_active=True).prefetch_related('schools', 'opening_hours')

    def get_context_data(self, **kwargs):
        """Add current period opening hours organized by day to context."""
        context = super().get_context_data(**kwargs)

        # Get current opening hours (from active period or default)
        current_hours = self.object.get_current_opening_hours()
        opening_hours = {}
        for hours in current_hours:
            day_name = hours.get_day_of_week_display()
            opening_hours[day_name] = hours

        context['opening_hours_by_day'] = opening_hours
        context['current_period'] = self.object.get_current_period()
        context['schools'] = self.object.schools.filter(status='Open').order_by('org_name')

        return context


class StoreCreateView(LoginRequiredMixin, SuperuserRequiredMixin, CreateView):
    """View for creating a new store."""
    model = Store
    form_class = StoreForm
    template_name = 'stores/store_form.html'

    def get_context_data(self, **kwargs):
        """Add context data."""
        context = super().get_context_data(**kwargs)
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        """Save the store."""
        self.object = form.save()
        messages.success(
            self.request,
            f'Store "{self.object.name}" created successfully! You can now add opening hours by managing periods.'
        )
        return redirect('stores:store_detail', pk=self.object.pk)

    def form_invalid(self, form):
        """Handle invalid form - errors are displayed inline in template."""
        return super().form_invalid(form)


class StoreUpdateView(LoginRequiredMixin, SuperuserRequiredMixin, UpdateView):
    """View for updating an existing store."""
    model = Store
    form_class = StoreForm
    template_name = 'stores/store_form.html'

    def get_context_data(self, **kwargs):
        """Add context data."""
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        return context

    def form_valid(self, form):
        """Save the store."""
        self.object = form.save()
        messages.success(self.request, f'Store "{self.object.name}" updated successfully!')
        return redirect('stores:store_detail', pk=self.object.pk)

    def form_invalid(self, form):
        """Handle invalid form - errors are displayed inline in template."""
        return super().form_invalid(form)


class StoreDeleteView(LoginRequiredMixin, SuperuserRequiredMixin, DeleteView):
    """View for deleting a store."""
    model = Store
    template_name = 'stores/store_confirm_delete.html'
    success_url = reverse_lazy('stores:store_list')

    def delete(self, request, *args, **kwargs):
        """Delete the store and show success message."""
        store_name = self.get_object().name
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Store "{store_name}" deleted successfully!')
        return response


class StorePeriodAssignmentView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    """View for assigning/unassigning periods to a specific store."""
    template_name = 'stores/store_assign_periods.html'

    def get_store(self):
        """Get the store object."""
        return get_object_or_404(Store, pk=self.kwargs['pk'])

    def get(self, request, *args, **kwargs):
        """Display the period assignment form."""
        store = self.get_store()
        form = StorePeriodAssignmentForm(store=store)

        # Categorize periods
        all_periods = StorePeriod.objects.all().prefetch_related('stores', 'opening_hours')
        assigned_periods = store.periods.all()
        today = date.today()

        # Group periods by status
        assigned_active = []
        assigned_upcoming = []
        assigned_past = []
        available_active = []
        available_upcoming = []
        available_past = []

        for period in all_periods:
            is_assigned = period in assigned_periods
            if period.is_currently_active():
                if is_assigned:
                    assigned_active.append(period)
                else:
                    available_active.append(period)
            elif period.is_future:
                if is_assigned:
                    assigned_upcoming.append(period)
                else:
                    available_upcoming.append(period)
            else:  # is_past
                if is_assigned:
                    assigned_past.append(period)
                else:
                    available_past.append(period)

        context = {
            'store': store,
            'form': form,
            'assigned_active': assigned_active,
            'assigned_upcoming': assigned_upcoming,
            'assigned_past': assigned_past,
            'available_active': available_active,
            'available_upcoming': available_upcoming,
            'available_past': available_past,
            'today': today,
        }

        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """Handle period assignment updates."""
        store = self.get_store()
        form = StorePeriodAssignmentForm(request.POST, store=store)

        if form.is_valid():
            with transaction.atomic():
                # Get selected periods from form
                new_periods = set(form.cleaned_data['periods'])
                # Get currently assigned periods
                old_periods = set(store.periods.all())

                # Periods to add (newly assigned)
                periods_to_add = new_periods - old_periods
                # Periods to remove (unassigned)
                periods_to_remove = old_periods - new_periods

                # Add new periods
                for period in periods_to_add:
                    store.periods.add(period)

                    # Check if period has existing opening hours from other stores
                    existing_hours = period.opening_hours.filter(
                        store__in=period.stores.exclude(pk=store.pk)
                    ).order_by('day_of_week')

                    if existing_hours.exists():
                        # Copy opening hours from first store that has them
                        # Group by day to get one set of hours
                        hours_by_day = {}
                        for hour in existing_hours:
                            if hour.day_of_week not in hours_by_day:
                                hours_by_day[hour.day_of_week] = hour

                        # Create opening hours for this store
                        for day, hour in hours_by_day.items():
                            StoreOpeningHours.objects.create(
                                store=store,
                                period=period,
                                day_of_week=hour.day_of_week,
                                opening_time=hour.opening_time,
                                closing_time=hour.closing_time,
                                is_closed=hour.is_closed,
                                notes=hour.notes
                            )

                # Remove unassigned periods
                for period in periods_to_remove:
                    # Delete opening hours for this store/period combination
                    StoreOpeningHours.objects.filter(store=store, period=period).delete()
                    # Remove the store from the period
                    store.periods.remove(period)

                # Success message
                if periods_to_add or periods_to_remove:
                    added_count = len(periods_to_add)
                    removed_count = len(periods_to_remove)
                    msg_parts = []
                    if added_count:
                        msg_parts.append(f"{added_count} period(s) assigned")
                    if removed_count:
                        msg_parts.append(f"{removed_count} period(s) unassigned")
                    messages.success(request, f"Successfully updated periods for {store.name}: {', '.join(msg_parts)}.")
                else:
                    messages.info(request, "No changes were made.")

            return redirect('stores:store_assign_periods', pk=store.pk)

        # If form is invalid, re-render with errors
        return self.get(request, *args, **kwargs)
