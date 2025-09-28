"""
Audit mixins for clubs application views
Provides reusable audit logging functionality for clubs operations
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


class ClubViewAuditMixin(AuditMixin):
    """
    Audit mixin for club views
    """

    def get_object(self, *args, **kwargs):
        """Override get_object to log club access"""
        obj = super().get_object(*args, **kwargs)

        if obj:
            # Determine action type based on club type
            if hasattr(obj, 'club_type'):
                if obj.club_type == 'LOTTO':
                    action_type = 'lotto_club_viewed'
                elif obj.club_type == 'SAS':
                    action_type = 'sas_club_viewed'
                else:
                    action_type = 'club_detail_viewed'
            else:
                action_type = 'club_detail_viewed'

            self.log_audit(
                action_type=action_type,
                description=f"Viewed club details: {obj.name}",
                club_id=obj.id,
                club_name=obj.name,
                club_type=getattr(obj, 'club_type', 'Unknown'),
                sport_tag=getattr(obj, 'sport_tag', ''),
                woo_category_id=getattr(obj, 'woo_category_id', None),
                total_categories=getattr(obj, 'categories', []).count() if hasattr(obj, 'categories') else 0,
                total_products=getattr(obj, 'total_products', 0),
                is_active=getattr(obj, 'is_active', True)
            )

        return obj

    def get_queryset(self):
        """Override get_queryset to potentially log list access"""
        queryset = super().get_queryset()

        # Log list view access (only for ListView, not DetailView)
        if hasattr(self, 'paginate_by') and hasattr(self, 'request'):
            search_query = self.request.GET.get('search', '') or self.request.GET.get('q', '')
            filters = {
                key: value for key, value in self.request.GET.items()
                if key in ['type', 'sport', 'club_type', 'status', 'sort']
                and value
            }

            # Determine action type based on filters
            club_type = filters.get('type') or filters.get('club_type')
            if club_type == 'LOTTO':
                action_type = 'lotto_club_searched' if search_query else 'club_list_viewed'
            elif club_type == 'SAS':
                action_type = 'sas_club_searched' if search_query else 'club_list_viewed'
            else:
                action_type = 'club_searched' if search_query else 'club_list_viewed'

            description = f"Searched clubs: '{search_query}'" if search_query else "Viewed clubs list"

            self.log_audit(
                action_type=action_type,
                description=description,
                search_query=search_query,
                filters=filters,
                total_count=queryset.count() if hasattr(queryset, 'count') else 0
            )

        return queryset


class ClubCategoryAuditMixin(AuditMixin):
    """
    Audit mixin for club category views
    """

    def get_object(self, *args, **kwargs):
        """Override get_object to log club category access"""
        obj = super().get_object(*args, **kwargs)

        if obj:
            # Determine action type based on club type
            club_type = getattr(obj.club, 'club_type', '') if hasattr(obj, 'club') else ''
            if club_type == 'LOTTO':
                action_type = 'lotto_category_viewed'
            elif club_type == 'SAS':
                action_type = 'sas_sport_viewed'  # SAS uses sports instead of categories
            else:
                action_type = 'club_category_viewed'

            self.log_audit(
                action_type=action_type,
                description=f"Viewed club category: {obj.name}",
                category_id=obj.id,
                category_name=obj.name,
                category_slug=getattr(obj, 'slug', ''),
                club_name=getattr(obj.club, 'name', '') if hasattr(obj, 'club') else '',
                club_type=club_type,
                woo_category_id=getattr(obj, 'woo_category_id', None),
                product_count=getattr(obj, 'product_count', 0)
            )

        return obj


class ClubProductAuditMixin(AuditMixin):
    """
    Audit mixin for club product views
    """

    def get_object(self, *args, **kwargs):
        """Override get_object to log club product access"""
        obj = super().get_object(*args, **kwargs)

        if obj:
            # Determine action type and club type
            primary_category = getattr(obj, 'primary_category', None)
            club_type = ''
            club_name = ''

            if primary_category and hasattr(primary_category, 'club'):
                club_type = getattr(primary_category.club, 'club_type', '')
                club_name = getattr(primary_category.club, 'name', '')

            if club_type == 'LOTTO':
                action_type = 'lotto_product_viewed'
            elif club_type == 'SAS':
                action_type = 'sas_product_viewed'
            else:
                action_type = 'club_product_viewed'

            self.log_audit(
                action_type=action_type,
                description=f"Viewed club product: {obj.name}",
                product_id=obj.id,
                product_name=obj.name,
                product_sku=getattr(obj, 'sku', ''),
                woo_product_id=getattr(obj, 'woo_product_id', None),
                club_name=club_name,
                club_type=club_type,
                category_name=getattr(primary_category, 'name', '') if primary_category else '',
                stock_status=getattr(obj, 'stock_status', ''),
                price=float(obj.price) if getattr(obj, 'price', None) else None,
                is_variable=getattr(obj, 'has_variations', False),
                total_variations=getattr(obj, 'variations', []).count() if hasattr(obj, 'variations') else 0
            )

        return obj


class ClubSearchAuditMixin(AuditMixin):
    """
    Audit mixin for club search operations
    """

    def get_queryset(self):
        """Override get_queryset to log search operations"""
        queryset = super().get_queryset()

        if hasattr(self, 'request'):
            search_query = self.request.GET.get('q', '') or self.request.GET.get('search', '')

            if search_query:
                # Determine search type based on view
                view_class_name = self.__class__.__name__.lower()

                if 'lotto' in view_class_name:
                    action_type = 'lotto_club_searched'
                    description = f"Searched LOTTO clubs: '{search_query}'"
                elif 'sas' in view_class_name:
                    action_type = 'sas_club_searched'
                    description = f"Searched SAS clubs: '{search_query}'"
                elif 'product' in view_class_name:
                    action_type = 'club_product_searched'
                    description = f"Searched club products: '{search_query}'"
                else:
                    action_type = 'club_searched'
                    description = f"Searched clubs: '{search_query}'"

                self.log_audit(
                    action_type=action_type,
                    description=description,
                    search_query=search_query,
                    search_length=len(search_query),
                    view_type=self.__class__.__name__
                )

        return queryset


class ClubSyncAuditMixin(AuditMixin):
    """
    Audit mixin for club sync operations
    """

    def log_sync_started(self, sync_type, **metadata):
        """Log sync operation start"""
        action_map = {
            'lotto': 'lotto_sync_started',
            'sas': 'sas_sync_started',
            'club': 'club_sync_started'
        }

        action_type = action_map.get(sync_type.lower(), 'club_sync_job_created')
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
            'lotto': 'lotto_sync_completed',
            'sas': 'sas_sync_completed',
            'club': 'club_sync_completed'
        }

        action_type = action_map.get(sync_type.lower(), 'club_sync_job_updated')
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
            'lotto': 'lotto_sync_failed',
            'sas': 'sas_sync_failed',
            'club': 'club_sync_failed'
        }

        action_type = action_map.get(sync_type.lower(), 'club_sync_job_updated')
        description = f"{sync_type.upper()} sync failed: {error_message}"

        return self.log_audit(
            action_type=action_type,
            description=description,
            sync_type=sync_type,
            error_message=error_message,
            **metadata
        )


class ClubBulkOperationAuditMixin(AuditMixin):
    """
    Audit mixin for club bulk operations
    """

    def log_bulk_update(self, operation_type, stats, **metadata):
        """Log bulk update operations"""
        action_type_map = {
            'club': 'club_bulk_update',
            'product': 'club_product_bulk_update',
            'category': 'club_category_bulk_update'
        }

        action_type = action_type_map.get(operation_type, 'club_bulk_update')
        successful = stats.get('successful_updates', 0)
        total = stats.get('total_processed', 0)

        return self.log_audit(
            action_type=action_type,
            description=f"Bulk updated {successful}/{total} {operation_type}s",
            operation_type=operation_type,
            update_stats=stats,
            **metadata
        )

    def log_bulk_delete(self, operation_type, count, **metadata):
        """Log bulk delete operations"""
        action_type_map = {
            'club': 'club_bulk_delete',
            'product': 'club_product_bulk_delete'
        }

        action_type = action_type_map.get(operation_type, 'club_bulk_delete')
        description = f"Bulk deleted {count} {operation_type}s"

        return self.log_audit(
            action_type=action_type,
            description=description,
            operation_type=operation_type,
            deleted_count=count,
            **metadata
        )


class ClubStockAuditMixin(AuditMixin):
    """
    Audit mixin for club stock operations
    """

    def log_stock_update(self, product, old_status, new_status, **metadata):
        """Log stock status changes"""
        if old_status != new_status:
            return self.log_audit(
                action_type='club_stock_status_changed',
                description=f"Stock status changed for {product.name}: {old_status} → {new_status}",
                product_id=product.id,
                product_name=product.name,
                old_status=old_status,
                new_status=new_status,
                **metadata
            )

    def log_variation_stock_update(self, variation, old_quantity, new_quantity, **metadata):
        """Log variation stock quantity changes"""
        if old_quantity != new_quantity:
            return self.log_audit(
                action_type='club_variation_stock_updated',
                description=f"Stock updated for {variation.product.name} ({variation.variation_value}): {old_quantity} → {new_quantity}",
                product_id=variation.product.id,
                variation_id=variation.id,
                variation_type=variation.variation_type,
                variation_value=variation.variation_value,
                old_quantity=old_quantity,
                new_quantity=new_quantity,
                **metadata
            )


class ClubImageAuditMixin(AuditMixin):
    """
    Audit mixin for club image operations
    """

    def log_image_upload(self, image_type, object_name, **metadata):
        """Log image upload operations"""
        action_type_map = {
            'club': 'club_image_uploaded',
            'product': 'club_product_image_uploaded',
            'variation': 'club_variation_image_uploaded'
        }

        action_type = action_type_map.get(image_type, 'club_image_uploaded')
        description = f"Uploaded {image_type} image for {object_name}"

        return self.log_audit(
            action_type=action_type,
            description=description,
            image_type=image_type,
            object_name=object_name,
            **metadata
        )

    def log_image_proxy_access(self, image_url, **metadata):
        """Log image proxy access"""
        return self.log_audit(
            action_type='club_image_proxy_accessed',
            description=f"Accessed image through proxy: {image_url[:100]}...",
            image_url=image_url,
            **metadata
        )


class AjaxAuditMixin(AuditMixin):
    """
    Audit mixin for AJAX operations in clubs
    """

    def log_ajax_search(self, query, results_count, search_type='club', **metadata):
        """Log AJAX search operations"""
        action_type_map = {
            'lotto': 'lotto_club_searched',
            'sas': 'sas_club_searched',
            'club': 'club_searched',
            'product': 'club_product_searched',
            'general': 'club_data_accessed'
        }

        action_type = action_type_map.get(search_type, 'club_data_accessed')
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
        # Determine club type based on product
        club_type = variation_data.get('club_type', 'unknown')

        if club_type == 'LOTTO':
            action_type = 'lotto_variation_checked'
        elif club_type == 'SAS':
            action_type = 'sas_variation_checked'
        else:
            action_type = 'club_product_variation_viewed'

        return self.log_audit(
            action_type=action_type,
            description=f"Checked product variations for product {product_id}",
            product_id=product_id,
            variation_data=variation_data,
            is_ajax=True,
            **metadata
        )