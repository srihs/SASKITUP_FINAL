"""
Signal handlers for schools application audit logging
Provides model-level audit logging for wholesale schools operations
"""
import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from authentication.models import AuditLog


logger = logging.getLogger(__name__)


def get_current_user():
    """
    Helper function to get current user from thread local storage
    Note: This requires middleware to set the user in thread local storage
    For now, we'll return None and rely on view-level audit logging
    """
    # TODO: Implement thread local user storage if needed
    return None


@receiver(post_save, sender='schools.WholesaleSchool')
def audit_wholesale_school_save(sender, instance, created, **kwargs):
    """Log wholesale school creation and updates"""
    try:
        user = get_current_user()

        if created:
            action_type = 'wholesale_school_created'
            description = f"Created wholesale school: {instance.name}"
        else:
            action_type = 'wholesale_school_updated'
            description = f"Updated wholesale school: {instance.name}"

        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            affected_model='WholesaleSchool',
            affected_object_id=str(instance.id),
            school_cin7_id=instance.cin7_id,
            school_name=instance.name,
            school_slug=instance.slug,
            is_active=instance.is_active,
            contact_person=instance.contact_person,
            city=instance.city,
            region=instance.region
        )

        logger.info(f"Audited wholesale school {'creation' if created else 'update'}: {instance.name}")

    except Exception as e:
        logger.error(f"Failed to audit wholesale school save: {str(e)}", exc_info=True)


@receiver(post_delete, sender='schools.WholesaleSchool')
def audit_wholesale_school_delete(sender, instance, **kwargs):
    """Log wholesale school deletion"""
    try:
        user = get_current_user()

        AuditLog.log_action(
            user=user,
            action_type='wholesale_school_deleted',
            description=f"Deleted wholesale school: {instance.name}",
            affected_model='WholesaleSchool',
            affected_object_id=str(instance.id),
            school_cin7_id=instance.cin7_id,
            school_name=instance.name,
            school_slug=instance.slug,
            contact_person=instance.contact_person,
            city=instance.city,
            region=instance.region
        )

        logger.info(f"Audited wholesale school deletion: {instance.name}")

    except Exception as e:
        logger.error(f"Failed to audit wholesale school deletion: {str(e)}", exc_info=True)


@receiver(post_save, sender='schools.WholesaleProduct')
def audit_wholesale_product_save(sender, instance, created, **kwargs):
    """Log wholesale product creation and updates"""
    try:
        user = get_current_user()

        if created:
            action_type = 'wholesale_product_created'
            description = f"Created wholesale product: {instance.name}"
        else:
            action_type = 'wholesale_product_updated'
            description = f"Updated wholesale product: {instance.name}"

        # Prepare metadata
        metadata = {
            'affected_model': 'WholesaleProduct',
            'affected_object_id': str(instance.id),
            'product_cin7_id': instance.cin7_id,
            'product_name': instance.name,
            'product_sku': instance.cin7_sku,
            'school_name': instance.school.name if instance.school else None,
            'school_cin7_id': instance.school.cin7_id if instance.school else None,
            'stock_status': instance.stock_status,
            'is_active': instance.is_active
        }

        # Add pricing information if available
        if instance.wholesale_price:
            metadata['wholesale_price'] = float(instance.wholesale_price)
        if instance.retail_price:
            metadata['retail_price'] = float(instance.retail_price)
        if instance.cost_price:
            metadata['cost_price'] = float(instance.cost_price)
        if hasattr(instance, 'margin_75_price') and instance.margin_75_price:
            metadata['margin_75_price'] = float(instance.margin_75_price)

        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            **metadata
        )

        logger.info(f"Audited wholesale product {'creation' if created else 'update'}: {instance.name}")

    except Exception as e:
        logger.error(f"Failed to audit wholesale product save: {str(e)}", exc_info=True)


@receiver(post_delete, sender='schools.WholesaleProduct')
def audit_wholesale_product_delete(sender, instance, **kwargs):
    """Log wholesale product deletion"""
    try:
        user = get_current_user()

        AuditLog.log_action(
            user=user,
            action_type='wholesale_product_deleted',
            description=f"Deleted wholesale product: {instance.name}",
            affected_model='WholesaleProduct',
            affected_object_id=str(instance.id),
            product_cin7_id=instance.cin7_id,
            product_name=instance.name,
            product_sku=instance.cin7_sku,
            school_name=instance.school.name if instance.school else None
        )

        logger.info(f"Audited wholesale product deletion: {instance.name}")

    except Exception as e:
        logger.error(f"Failed to audit wholesale product deletion: {str(e)}", exc_info=True)


@receiver(post_save, sender='schools.WholesaleCategory')
def audit_wholesale_category_save(sender, instance, created, **kwargs):
    """Log wholesale category creation and updates"""
    try:
        user = get_current_user()

        if created:
            action_type = 'wholesale_category_created'
            description = f"Created wholesale category: {instance.name}"
        else:
            action_type = 'wholesale_category_updated'
            description = f"Updated wholesale category: {instance.name}"

        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            affected_model='WholesaleCategory',
            affected_object_id=str(instance.id),
            category_cin7_id=instance.cin7_id,
            category_name=instance.name,
            category_level=instance.level,
            parent_category=instance.parent.name if instance.parent else None,
            product_count=instance.product_count,
            is_active=instance.is_active
        )

        logger.info(f"Audited wholesale category {'creation' if created else 'update'}: {instance.name}")

    except Exception as e:
        logger.error(f"Failed to audit wholesale category save: {str(e)}", exc_info=True)


@receiver(post_save, sender='schools.WholesaleProductVariation')
def audit_wholesale_variation_save(sender, instance, created, **kwargs):
    """Log wholesale product variation creation and updates"""
    try:
        user = get_current_user()

        if created:
            action_type = 'wholesale_variation_created'
            description = f"Created product variation: {instance.variation_type} - {instance.variation_value}"
        else:
            action_type = 'wholesale_variation_updated'
            description = f"Updated product variation: {instance.variation_type} - {instance.variation_value}"

        # Prepare metadata
        metadata = {
            'affected_model': 'WholesaleProductVariation',
            'affected_object_id': str(instance.id),
            'variation_cin7_id': instance.cin7_id,
            'variation_type': instance.variation_type,
            'variation_value': instance.variation_value,
            'product_name': instance.product.name if instance.product else None,
            'product_cin7_id': instance.product.cin7_id if instance.product else None,
            'is_active': instance.is_active
        }

        # Add pricing information if available
        if instance.wholesale_price:
            metadata['wholesale_price'] = float(instance.wholesale_price)
        if instance.retail_price:
            metadata['retail_price'] = float(instance.retail_price)
        if instance.cost_price:
            metadata['cost_price'] = float(instance.cost_price)

        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            **metadata
        )

        logger.info(f"Audited wholesale variation {'creation' if created else 'update'}: {instance.variation_type} - {instance.variation_value}")

    except Exception as e:
        logger.error(f"Failed to audit wholesale variation save: {str(e)}", exc_info=True)


@receiver(post_save, sender='schools.WholesaleSyncJob')
def audit_sync_job_save(sender, instance, created, **kwargs):
    """Log wholesale sync job creation and updates"""
    try:
        user = get_current_user()

        if created:
            action_type = 'sync_job_created'
            description = f"Created wholesale sync job"
        else:
            # Determine action based on status change
            if instance.status == 'completed':
                action_type = 'wholesale_sync_completed'
                description = f"Wholesale sync completed successfully"
            elif instance.status == 'failed':
                action_type = 'wholesale_sync_failed'
                description = f"Wholesale sync failed"
            elif instance.status == 'cancelled':
                action_type = 'sync_job_cancelled'
                description = f"Wholesale sync job cancelled"
            else:
                action_type = 'sync_job_updated'
                description = f"Wholesale sync job updated"

        # Prepare statistics metadata
        sync_stats = {
            'schools_created': instance.schools_created,
            'schools_updated': instance.schools_updated,
            'products_created': instance.products_created,
            'products_updated': instance.products_updated,
            'categories_created': instance.categories_created,
            'categories_updated': instance.categories_updated,
            'variations_created': instance.variations_created,
            'variations_updated': instance.variations_updated,
            'errors_count': instance.errors_count
        }

        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            affected_model='WholesaleSyncJob',
            affected_object_id=str(instance.id),
            sync_job_id=str(instance.id),
            sync_status=instance.status,
            progress_percentage=instance.progress_percentage,
            current_step=instance.current_step,
            sync_stats=sync_stats,
            duration_seconds=(instance.completed_at - instance.started_at).total_seconds() if instance.started_at and instance.completed_at else None
        )

        logger.info(f"Audited wholesale sync job {'creation' if created else 'update'}: {instance.status}")

    except Exception as e:
        logger.error(f"Failed to audit wholesale sync job save: {str(e)}", exc_info=True)


# Price update tracking
@receiver(pre_save, sender='schools.WholesaleProduct')
def track_price_changes(sender, instance, **kwargs):
    """Track price changes for audit purposes"""
    try:
        if instance.pk:  # Only for updates, not creation
            try:
                old_instance = sender.objects.get(pk=instance.pk)

                # Check if any pricing field has changed
                price_changes = {}

                if old_instance.wholesale_price != instance.wholesale_price:
                    price_changes['wholesale_price'] = {
                        'old': float(old_instance.wholesale_price) if old_instance.wholesale_price else None,
                        'new': float(instance.wholesale_price) if instance.wholesale_price else None
                    }

                if old_instance.retail_price != instance.retail_price:
                    price_changes['retail_price'] = {
                        'old': float(old_instance.retail_price) if old_instance.retail_price else None,
                        'new': float(instance.retail_price) if instance.retail_price else None
                    }

                if old_instance.cost_price != instance.cost_price:
                    price_changes['cost_price'] = {
                        'old': float(old_instance.cost_price) if old_instance.cost_price else None,
                        'new': float(instance.cost_price) if instance.cost_price else None
                    }

                # Check margin_75_price if it exists
                if hasattr(old_instance, 'margin_75_price') and hasattr(instance, 'margin_75_price'):
                    if old_instance.margin_75_price != instance.margin_75_price:
                        price_changes['margin_75_price'] = {
                            'old': float(old_instance.margin_75_price) if old_instance.margin_75_price else None,
                            'new': float(instance.margin_75_price) if instance.margin_75_price else None
                        }

                # Log price update if any prices changed
                if price_changes:
                    user = get_current_user()

                    AuditLog.log_action(
                        user=user,
                        action_type='wholesale_price_update',
                        description=f"Updated prices for product: {instance.name}",
                        affected_model='WholesaleProduct',
                        affected_object_id=str(instance.id),
                        product_name=instance.name,
                        product_sku=instance.cin7_sku,
                        school_name=instance.school.name if instance.school else None,
                        price_changes=price_changes,
                        change_timestamp=timezone.now().isoformat()
                    )

                    logger.info(f"Audited price update for product: {instance.name}")

            except sender.DoesNotExist:
                # Object doesn't exist yet, this is a creation
                pass

    except Exception as e:
        logger.error(f"Failed to track price changes: {str(e)}", exc_info=True)


# Helper function to register signal handlers
def register_audit_signals():
    """
    Register all audit signal handlers
    This function should be called in the app's ready() method
    """
    logger.info("Registered schools audit signal handlers")