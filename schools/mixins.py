"""
Audit mixins for schools application views
Provides reusable audit logging functionality for schools operations
"""
import logging
from django.utils import timezone
from authentication.models import AuditLog


logger = logging.getLogger(__name__)


class AuditMixin:
    """
    Base audit mixin providing core audit functionality
    """

    def log_audit(self, action_type, description, **metadata):
        """
        Log an audit event with optional metadata

        Args:
            action_type: Action type from AuditLog.ACTION_TYPES
            description: Human-readable description of the action
            **metadata: Additional metadata to store
        """
        try:
            # Get request from the view
            request = getattr(self, 'request', None)
            user = None

            if request and hasattr(request, 'user'):
                # Only use authenticated users, not AnonymousUser
                if request.user.is_authenticated:
                    user = request.user

            # Add common metadata
            audit_metadata = {
                'view_class': self.__class__.__name__,
                'timestamp': timezone.now().isoformat(),
                **metadata
            }

            # If we have an object, add its details
            if hasattr(self, 'object') and self.object:
                audit_metadata.update({
                    'affected_model': self.object.__class__.__name__,
                    'affected_object_id': str(getattr(self.object, 'id', getattr(self.object, 'pk', ''))),
                })

            return AuditLog.log_action(
                user=user,
                action_type=action_type,
                description=description,
                request=request,
                **audit_metadata
            )

        except Exception as e:
            logger.error(f"Failed to log audit event: {str(e)}", exc_info=True)
            return None


class SchoolViewAuditMixin(AuditMixin):
    """
    Audit mixin for regular school views
    """

    def get_object(self, *args, **kwargs):
        """Override get_object to log school access"""
        obj = super().get_object(*args, **kwargs)

        if obj:
            self.log_audit(
                action_type='school_detail_viewed',
                description=f"Viewed school details: {obj.org_name}",
                school_id=obj.school_id,
                school_name=obj.org_name,
                school_type=obj.org_type,
                region=obj.regional_council
            )

        return obj

    def get_queryset(self):
        """Override get_queryset to potentially log list access"""
        queryset = super().get_queryset()

        # Log list view access (only for ListView, not DetailView)
        if hasattr(self, 'paginate_by') and hasattr(self, 'request'):
            search_query = self.request.GET.get('q', '')
            filters = {
                key: value for key, value in self.request.GET.items()
                if key in ['org_type', 'regional_council', 'authority', 'status', 'sort']
                and value
            }

            self.log_audit(
                action_type='school_list_viewed',
                description="Viewed schools list",
                search_query=search_query,
                filters=filters,
                total_count=queryset.count() if hasattr(queryset, 'count') else 0
            )

        return queryset


class WholesaleAuditMixin(AuditMixin):
    """
    Audit mixin for wholesale operations
    """

    def get_object(self, *args, **kwargs):
        """Override get_object to log wholesale entity access"""
        obj = super().get_object(*args, **kwargs)

        if obj:
            # Determine the action type based on object type
            if hasattr(obj, 'cin7_id'):  # WholesaleSchool, WholesaleProduct, etc.
                if 'school' in obj.__class__.__name__.lower():
                    action_type = 'wholesale_school_viewed'
                    description = f"Viewed wholesale school: {obj.name}"
                    metadata = {
                        'school_id': obj.cin7_id,
                        'school_name': obj.name,
                        'school_slug': getattr(obj, 'slug', ''),
                        'total_products': getattr(obj, 'total_products', 0)
                    }
                elif 'product' in obj.__class__.__name__.lower():
                    action_type = 'wholesale_product_viewed'
                    description = f"Viewed wholesale product: {obj.name}"
                    metadata = {
                        'product_id': obj.cin7_id,
                        'product_name': obj.name,
                        'product_sku': getattr(obj, 'cin7_sku', ''),
                        'school_name': getattr(obj.school, 'name', '') if hasattr(obj, 'school') else '',
                        'stock_status': getattr(obj, 'stock_status', ''),
                        'wholesale_price': float(obj.wholesale_price) if getattr(obj, 'wholesale_price', None) else None
                    }
                elif 'category' in obj.__class__.__name__.lower():
                    action_type = 'wholesale_category_viewed'
                    description = f"Viewed wholesale category: {obj.name}"
                    metadata = {
                        'category_id': obj.cin7_id,
                        'category_name': obj.name,
                        'category_level': getattr(obj, 'level', 0),
                        'product_count': getattr(obj, 'product_count', 0)
                    }
                else:
                    action_type = 'data_access'
                    description = f"Viewed wholesale entity: {obj.name}"
                    metadata = {'entity_type': obj.__class__.__name__}

                self.log_audit(action_type=action_type, description=description, **metadata)

        return obj


class TUSAuditMixin(AuditMixin):
    """
    Audit mixin for TUS retail operations
    """

    def get_object(self, *args, **kwargs):
        """Override get_object to log TUS entity access"""
        obj = super().get_object(*args, **kwargs)

        if obj:
            # Determine the action type based on object type
            obj_class = obj.__class__.__name__.lower()

            if 'location' in obj_class:
                action_type = 'tus_location_viewed'
                description = f"Viewed TUS location: {obj.name}"
                metadata = {
                    'location_slug': getattr(obj, 'slug', ''),
                    'location_name': obj.name,
                    'total_schools': getattr(obj, 'total_schools', 0)
                }
            elif 'school' in obj_class:
                action_type = 'tus_school_viewed'
                description = f"Viewed TUS school: {obj.name}"
                metadata = {
                    'school_slug': getattr(obj, 'slug', ''),
                    'school_name': obj.name,
                    'school_type': getattr(obj, 'school_type', ''),
                    'location_name': getattr(obj.location, 'name', '') if hasattr(obj, 'location') else '',
                    'total_products': getattr(obj, 'total_products', 0)
                }
            elif 'category' in obj_class:
                action_type = 'tus_category_viewed'
                description = f"Viewed TUS category: {obj.name}"
                metadata = {
                    'category_slug': getattr(obj, 'slug', ''),
                    'category_name': obj.name,
                    'school_name': getattr(obj.school, 'name', '') if hasattr(obj, 'school') else '',
                    'product_count': getattr(obj, 'product_count', 0)
                }
            elif 'product' in obj_class:
                action_type = 'tus_product_viewed'
                description = f"Viewed TUS product: {obj.name}"
                metadata = {
                    'product_id': getattr(obj, 'id', ''),
                    'product_name': obj.name,
                    'product_sku': getattr(obj, 'sku', ''),
                    'price': float(obj.price) if getattr(obj, 'price', None) else None,
                    'stock_status': getattr(obj, 'stock_status', '')
                }
            else:
                action_type = 'data_access'
                description = f"Viewed TUS entity: {getattr(obj, 'name', str(obj))}"
                metadata = {'entity_type': obj.__class__.__name__}

            self.log_audit(action_type=action_type, description=description, **metadata)

        return obj


class SearchAuditMixin(AuditMixin):
    """
    Audit mixin for search operations
    """

    def get_queryset(self):
        """Override get_queryset to log search operations"""
        queryset = super().get_queryset()

        if hasattr(self, 'request'):
            search_query = self.request.GET.get('q', '') or self.request.GET.get('search', '')

            if search_query:
                # Determine search type based on view
                if 'wholesale' in self.__class__.__name__.lower():
                    action_type = 'wholesale_school_searched'
                    description = f"Searched wholesale schools: '{search_query}'"
                elif 'tus' in self.__class__.__name__.lower():
                    action_type = 'tus_search_performed'
                    description = f"Performed TUS search: '{search_query}'"
                else:
                    action_type = 'school_searched'
                    description = f"Searched schools: '{search_query}'"

                self.log_audit(
                    action_type=action_type,
                    description=description,
                    search_query=search_query,
                    search_length=len(search_query),
                    view_type=self.__class__.__name__
                )

        return queryset


class SyncAuditMixin(AuditMixin):
    """
    Audit mixin for sync operations
    """

    def log_sync_started(self, sync_type, **metadata):
        """Log sync operation start"""
        action_map = {
            'wholesale': 'wholesale_sync_started',
            'tus': 'tus_sync_started'
        }

        action_type = action_map.get(sync_type, 'sync_job_created')
        description = f"{sync_type.upper()} sync started"

        return self.log_audit(
            action_type=action_type,
            description=description,
            sync_type=sync_type,
            **metadata
        )

    def log_sync_completed(self, sync_type, stats=None, **metadata):
        """Log sync operation completion"""
        action_map = {
            'wholesale': 'wholesale_sync_completed',
            'tus': 'tus_sync_completed'
        }

        action_type = action_map.get(sync_type, 'sync_job_updated')
        description = f"{sync_type.upper()} sync completed successfully"

        audit_metadata = {'sync_type': sync_type, **metadata}
        if stats:
            audit_metadata['sync_stats'] = stats

        return self.log_audit(
            action_type=action_type,
            description=description,
            **audit_metadata
        )

    def log_sync_failed(self, sync_type, error_message, **metadata):
        """Log sync operation failure"""
        action_map = {
            'wholesale': 'wholesale_sync_failed',
            'tus': 'tus_sync_failed'
        }

        action_type = action_map.get(sync_type, 'sync_job_updated')
        description = f"{sync_type.upper()} sync failed: {error_message}"

        return self.log_audit(
            action_type=action_type,
            description=description,
            sync_type=sync_type,
            error_message=error_message,
            **metadata
        )


class PriceUpdateAuditMixin(AuditMixin):
    """
    Audit mixin for wholesale price update operations
    """

    def log_price_preview(self, preview_stats, **metadata):
        """Log price preview operation"""
        return self.log_audit(
            action_type='wholesale_price_preview',
            description=f"Generated price preview for {preview_stats.get('total_rows', 0)} products",
            preview_stats=preview_stats,
            **metadata
        )

    def log_price_update(self, update_stats, **metadata):
        """Log price update operation"""
        successful = update_stats.get('successful_updates', 0)
        total = update_stats.get('total_processed', 0)

        return self.log_audit(
            action_type='wholesale_price_bulk_update',
            description=f"Updated prices for {successful}/{total} products",
            update_stats=update_stats,
            **metadata
        )

    def log_price_settings_access(self, **metadata):
        """Log access to price settings"""
        return self.log_audit(
            action_type='wholesale_price_settings_accessed',
            description="Accessed wholesale price update settings",
            **metadata
        )


class CSVAuditMixin(AuditMixin):
    """
    Audit mixin for CSV operations
    """

    def log_csv_upload(self, filename, file_size, **metadata):
        """Log CSV file upload"""
        return self.log_audit(
            action_type='csv_upload_started',
            description=f"Started CSV upload: {filename}",
            filename=filename,
            file_size=file_size,
            **metadata
        )

    def log_csv_import_completed(self, filename, stats, **metadata):
        """Log CSV import completion"""
        return self.log_audit(
            action_type='csv_import_completed',
            description=f"Completed CSV import: {filename}",
            filename=filename,
            import_stats=stats,
            **metadata
        )

    def log_csv_import_failed(self, filename, error_message, **metadata):
        """Log CSV import failure"""
        return self.log_audit(
            action_type='csv_import_failed',
            description=f"Failed CSV import: {filename} - {error_message}",
            filename=filename,
            error_message=error_message,
            **metadata
        )


class AjaxAuditMixin(AuditMixin):
    """
    Audit mixin for AJAX operations
    """

    def log_ajax_search(self, query, results_count, search_type='general', **metadata):
        """Log AJAX search operations"""
        action_type_map = {
            'tus': 'tus_search_performed',
            'wholesale': 'wholesale_school_searched',
            'school': 'school_searched',
            'general': 'data_access'
        }

        action_type = action_type_map.get(search_type, 'data_access')
        description = f"AJAX search performed: '{query}' ({results_count} results)"

        return self.log_audit(
            action_type=action_type,
            description=description,
            search_query=query,
            results_count=results_count,
            search_type=search_type,
            is_ajax=True,
            **metadata
        )

    def log_variation_check(self, product_id, variation_data, **metadata):
        """Log product variation checks"""
        return self.log_audit(
            action_type='tus_variation_checked',
            description=f"Checked product variations for product {product_id}",
            product_id=product_id,
            variation_data=variation_data,
            is_ajax=True,
            **metadata
        )