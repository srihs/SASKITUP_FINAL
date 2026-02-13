from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.db import transaction
from datetime import date
from .models import Store, StorePeriod, StoreOpeningHours
from .period_forms import StorePeriodForm, PeriodOpeningHoursFormSet


class SuperuserRequiredMixin(UserPassesTestMixin):
    """Mixin to require superuser access."""
    def test_func(self):
        return self.request.user.is_superuser


class StorePeriodListView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
    """View for listing all periods across all stores."""
    model = StorePeriod
    template_name = 'stores/period_list.html'
    context_object_name = 'periods'

    def get_queryset(self):
        """Return all periods with prefetched stores and opening hours."""
        return StorePeriod.objects.all().prefetch_related('stores', 'opening_hours')

    def get_context_data(self, **kwargs):
        """Add current date and categorized periods to context."""
        context = super().get_context_data(**kwargs)
        context['today'] = date.today()
        context['stores'] = Store.objects.all().order_by('name')

        # Categorize periods
        context['active_periods'] = [p for p in context['periods'] if p.is_currently_active()]
        context['upcoming_periods'] = [p for p in context['periods'] if p.is_future]
        context['past_periods'] = [p for p in context['periods'] if p.is_past]

        return context


class StorePeriodCreateView(LoginRequiredMixin, SuperuserRequiredMixin, CreateView):
    """View for creating a new period."""
    model = StorePeriod
    form_class = StorePeriodForm
    template_name = 'stores/period_form.html'

    def get_context_data(self, **kwargs):
        """Add formset for opening hours."""
        context = super().get_context_data(**kwargs)

        if self.request.POST:
            context['opening_hours_formset'] = PeriodOpeningHoursFormSet(
                self.request.POST,
                instance=self.object
            )
        else:
            # Pre-populate formset with all 7 days
            context['opening_hours_formset'] = PeriodOpeningHoursFormSet(
                instance=self.object,
                initial=[
                    {'day_of_week': 0},  # Monday
                    {'day_of_week': 1},  # Tuesday
                    {'day_of_week': 2},  # Wednesday
                    {'day_of_week': 3},  # Thursday
                    {'day_of_week': 4},  # Friday
                    {'day_of_week': 5},  # Saturday
                    {'day_of_week': 6},  # Sunday
                ]
            )
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        """Save the period and opening hours."""
        context = self.get_context_data()
        opening_hours_formset = context['opening_hours_formset']

        with transaction.atomic():
            # Save the period (including M2M stores field)
            self.object = form.save()

            if opening_hours_formset.is_valid():
                opening_hours_formset.instance = self.object
                # Set store for each opening hours instance
                instances = opening_hours_formset.save(commit=False)

                # Only create opening hours if stores are selected
                if self.object.stores.exists():
                    # Create opening hours for each selected store
                    for store in self.object.stores.all():
                        for instance in instances:
                            # Clone the instance for each store
                            StoreOpeningHours.objects.create(
                                store=store,
                                period=self.object,
                                day_of_week=instance.day_of_week,
                                opening_time=instance.opening_time,
                                closing_time=instance.closing_time,
                                is_closed=instance.is_closed,
                                notes=instance.notes
                            )
                    messages.success(self.request, f'Period "{self.object.name}" created successfully with {self.object.stores.count()} store(s)!')
                else:
                    messages.success(self.request, f'Period "{self.object.name}" created successfully! You can assign stores later.')

                return redirect('stores:period_list')
            else:
                return self.form_invalid(form)

    def form_invalid(self, form):
        """Handle invalid form."""
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class StorePeriodUpdateView(LoginRequiredMixin, SuperuserRequiredMixin, UpdateView):
    """View for updating an existing period."""
    model = StorePeriod
    form_class = StorePeriodForm
    template_name = 'stores/period_form.html'
    pk_url_kwarg = 'pk'

    def get_context_data(self, **kwargs):
        """Add formset for opening hours."""
        context = super().get_context_data(**kwargs)

        if self.request.POST:
            context['opening_hours_formset'] = PeriodOpeningHoursFormSet(
                self.request.POST,
                instance=self.object
            )
        else:
            # Get opening hours for the first store (or create initial data)
            first_store = self.object.stores.first()
            if first_store:
                # Use existing hours from first store as template
                context['opening_hours_formset'] = PeriodOpeningHoursFormSet(
                    instance=self.object,
                    queryset=StoreOpeningHours.objects.filter(period=self.object, store=first_store)
                )
            else:
                context['opening_hours_formset'] = PeriodOpeningHoursFormSet(
                    instance=self.object
                )
        context['is_edit'] = True
        return context

    def form_valid(self, form):
        """Save the period and opening hours."""
        context = self.get_context_data()
        opening_hours_formset = context['opening_hours_formset']

        with transaction.atomic():
            # Get old stores before saving
            old_stores = set(self.object.stores.all())

            # Save the period (including updated M2M stores field)
            self.object = form.save()

            # Get new stores after saving
            new_stores = set(self.object.stores.all())

            # Stores that were removed
            removed_stores = old_stores - new_stores
            # Stores that were added
            added_stores = new_stores - old_stores

            if opening_hours_formset.is_valid():
                # Delete opening hours for removed stores
                for store in removed_stores:
                    StoreOpeningHours.objects.filter(period=self.object, store=store).delete()

                # Update opening hours for existing stores and create for new stores
                opening_hours_formset.instance = self.object
                instances = opening_hours_formset.save(commit=False)

                # Update all stores with the new hours
                for store in new_stores:
                    # Delete existing hours for this store/period
                    StoreOpeningHours.objects.filter(period=self.object, store=store).delete()
                    # Create new hours
                    for instance in instances:
                        StoreOpeningHours.objects.create(
                            store=store,
                            period=self.object,
                            day_of_week=instance.day_of_week,
                            opening_time=instance.opening_time,
                            closing_time=instance.closing_time,
                            is_closed=instance.is_closed,
                            notes=instance.notes
                        )

                messages.success(self.request, f'Period "{self.object.name}" updated successfully!')
                return redirect('stores:period_list')
            else:
                return self.form_invalid(form)

    def form_invalid(self, form):
        """Handle invalid form."""
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class StorePeriodDeleteView(LoginRequiredMixin, SuperuserRequiredMixin, DeleteView):
    """View for deleting a period."""
    model = StorePeriod
    template_name = 'stores/period_confirm_delete.html'
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('stores:period_list')

    def delete(self, request, *args, **kwargs):
        """Delete the period and show success message."""
        period_name = self.get_object().name
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f'Period "{period_name}" deleted successfully!')
        return response
