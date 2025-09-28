"""
Django signals for clubs application
Provides automatic audit logging for model-level operations
"""
import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from authentication.models import AuditLog
from .models import Club, ClubCategory, Product, ProductVariation, ProductCategoryAssignment, SyncJob


logger = logging.getLogger(__name__)
User = get_user_model()


def get_current_user():
    """
    Get current user from thread local storage or return None
    This is a fallback for when signals are triggered outside of request context
    """
    try:
        from threading import current_thread
        thread = current_thread()
        return getattr(thread, 'user', None)
    except:
        return None


@receiver(post_save, sender=Club)
def log_club_save(sender, instance, created, **kwargs):
    """Log club creation and updates"""
    user = get_current_user()

    if created:
        action_type = 'club_created'
        description = f"Created club: {instance.name}"
    else:
        action_type = 'club_updated'
        description = f"Updated club: {instance.name}"

    try:
        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            club_id=instance.id,
            club_name=instance.name,
            club_type=instance.club_type,
            sport_tag=instance.sport_tag,
            woo_category_id=instance.woo_category_id,
            is_active=instance.is_active,
            total_categories=instance.categories.count() if hasattr(instance, 'categories') else 0,
            affected_model='Club',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged {action_type} for club {instance.name}")
    except Exception as e:
        logger.error(f"Failed to log {action_type} for club {instance.name}: {str(e)}")


@receiver(post_delete, sender=Club)
def log_club_delete(sender, instance, **kwargs):
    """Log club deletion"""
    user = get_current_user()

    try:
        AuditLog.log_action(
            user=user,
            action_type='club_deleted',
            description=f"Deleted club: {instance.name}",
            club_id=instance.id,
            club_name=instance.name,
            club_type=instance.club_type,
            sport_tag=instance.sport_tag,
            woo_category_id=instance.woo_category_id,
            affected_model='Club',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged club_deleted for club {instance.name}")
    except Exception as e:
        logger.error(f"Failed to log club_deleted for club {instance.name}: {str(e)}")


@receiver(post_save, sender=ClubCategory)
def log_club_category_save(sender, instance, created, **kwargs):
    """Log club category creation and updates"""
    user = get_current_user()

    if created:
        action_type = 'club_category_created'
        description = f"Created category: {instance.name} for club {instance.club.name}"
    else:
        action_type = 'club_category_updated'
        description = f"Updated category: {instance.name} for club {instance.club.name}"

    try:
        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            category_id=instance.id,
            category_name=instance.name,
            club_id=instance.club.id,
            club_name=instance.club.name,
            club_type=instance.club.club_type,
            woo_category_id=instance.woo_category_id,
            product_count=instance.product_count,
            affected_model='ClubCategory',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged {action_type} for category {instance.name}")
    except Exception as e:
        logger.error(f"Failed to log {action_type} for category {instance.name}: {str(e)}")


@receiver(post_delete, sender=ClubCategory)
def log_club_category_delete(sender, instance, **kwargs):
    """Log club category deletion"""
    user = get_current_user()

    try:
        AuditLog.log_action(
            user=user,
            action_type='club_category_deleted',
            description=f"Deleted category: {instance.name} from club {instance.club.name}",
            category_id=instance.id,
            category_name=instance.name,
            club_id=instance.club.id,
            club_name=instance.club.name,
            club_type=instance.club.club_type,
            woo_category_id=instance.woo_category_id,
            affected_model='ClubCategory',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged club_category_deleted for category {instance.name}")
    except Exception as e:
        logger.error(f"Failed to log club_category_deleted for category {instance.name}: {str(e)}")


@receiver(post_save, sender=Product)
def log_product_save(sender, instance, created, **kwargs):
    """Log product creation and updates"""
    user = get_current_user()

    if created:
        action_type = 'club_product_created'
        description = f"Created product: {instance.name}"
    else:
        action_type = 'club_product_updated'
        description = f"Updated product: {instance.name}"

    try:
        primary_category = instance.primary_category
        club_name = getattr(primary_category.club, 'name', '') if primary_category else ''
        club_type = getattr(primary_category.club, 'club_type', '') if primary_category else ''

        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            product_id=instance.id,
            product_name=instance.name,
            product_sku=instance.sku or '',
            woo_product_id=instance.woo_product_id,
            price=float(instance.price) if instance.price else None,
            stock_status=instance.stock_status,
            club_name=club_name,
            club_type=club_type,
            category_name=getattr(primary_category, 'name', '') if primary_category else '',
            has_variations=instance.has_variations,
            total_categories=instance.categories.count(),
            affected_model='Product',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged {action_type} for product {instance.name}")
    except Exception as e:
        logger.error(f"Failed to log {action_type} for product {instance.name}: {str(e)}")


@receiver(post_delete, sender=Product)
def log_product_delete(sender, instance, **kwargs):
    """Log product deletion"""
    user = get_current_user()

    try:
        AuditLog.log_action(
            user=user,
            action_type='club_product_deleted',
            description=f"Deleted product: {instance.name}",
            product_id=instance.id,
            product_name=instance.name,
            product_sku=instance.sku or '',
            woo_product_id=instance.woo_product_id,
            affected_model='Product',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged club_product_deleted for product {instance.name}")
    except Exception as e:
        logger.error(f"Failed to log club_product_deleted for product {instance.name}: {str(e)}")


@receiver(post_save, sender=ProductVariation)
def log_product_variation_save(sender, instance, created, **kwargs):
    """Log product variation creation and updates"""
    user = get_current_user()

    if created:
        action_type = 'club_product_variation_created'
        description = f"Created variation: {instance.variation_value} for product {instance.product.name}"
    else:
        action_type = 'club_product_variation_updated'
        description = f"Updated variation: {instance.variation_value} for product {instance.product.name}"

    try:
        primary_category = instance.product.primary_category
        club_name = getattr(primary_category.club, 'name', '') if primary_category else ''
        club_type = getattr(primary_category.club, 'club_type', '') if primary_category else ''

        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            variation_id=instance.id,
            variation_type=instance.variation_type,
            variation_value=instance.variation_value,
            product_id=instance.product.id,
            product_name=instance.product.name,
            woo_variation_id=instance.woo_variation_id,
            price_modifier=float(instance.price_modifier),
            stock_quantity=instance.stock_quantity,
            club_name=club_name,
            club_type=club_type,
            is_active=instance.is_active,
            affected_model='ProductVariation',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged {action_type} for variation {instance.variation_value}")
    except Exception as e:
        logger.error(f"Failed to log {action_type} for variation {instance.variation_value}: {str(e)}")


@receiver(post_delete, sender=ProductVariation)
def log_product_variation_delete(sender, instance, **kwargs):
    """Log product variation deletion"""
    user = get_current_user()

    try:
        AuditLog.log_action(
            user=user,
            action_type='club_product_variation_deleted',
            description=f"Deleted variation: {instance.variation_value} from product {instance.product.name}",
            variation_id=instance.id,
            variation_type=instance.variation_type,
            variation_value=instance.variation_value,
            product_id=instance.product.id,
            product_name=instance.product.name,
            woo_variation_id=instance.woo_variation_id,
            affected_model='ProductVariation',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged club_product_variation_deleted for variation {instance.variation_value}")
    except Exception as e:
        logger.error(f"Failed to log club_product_variation_deleted for variation {instance.variation_value}: {str(e)}")


@receiver(post_save, sender=ProductCategoryAssignment)
def log_product_category_assignment(sender, instance, created, **kwargs):
    """Log product category assignments"""
    user = get_current_user()

    if created:
        action_type = 'club_product_category_assigned'
        description = f"Assigned product {instance.product.name} to category {instance.category.name}"
    else:
        action_type = 'club_product_category_primary_changed' if instance.is_primary else 'club_product_category_assigned'
        description = f"Updated assignment of product {instance.product.name} to category {instance.category.name}"

    try:
        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            product_id=instance.product.id,
            product_name=instance.product.name,
            category_id=instance.category.id,
            category_name=instance.category.name,
            club_id=instance.category.club.id,
            club_name=instance.category.club.name,
            club_type=instance.category.club.club_type,
            is_primary=instance.is_primary,
            sort_order=instance.sort_order,
            woo_category_id=instance.woo_category_id,
            affected_model='ProductCategoryAssignment',
            affected_object_id=str(instance.product.id) + '_' + str(instance.category.id)
        )
        logger.info(f"Logged {action_type} for product {instance.product.name}")
    except Exception as e:
        logger.error(f"Failed to log {action_type} for product {instance.product.name}: {str(e)}")


@receiver(post_delete, sender=ProductCategoryAssignment)
def log_product_category_unassignment(sender, instance, **kwargs):
    """Log product category unassignments"""
    user = get_current_user()

    try:
        AuditLog.log_action(
            user=user,
            action_type='club_product_category_unassigned',
            description=f"Unassigned product {instance.product.name} from category {instance.category.name}",
            product_id=instance.product.id,
            product_name=instance.product.name,
            category_id=instance.category.id,
            category_name=instance.category.name,
            club_id=instance.category.club.id,
            club_name=instance.category.club.name,
            club_type=instance.category.club.club_type,
            was_primary=instance.is_primary,
            affected_model='ProductCategoryAssignment',
            affected_object_id=str(instance.product.id) + '_' + str(instance.category.id)
        )
        logger.info(f"Logged club_product_category_unassigned for product {instance.product.name}")
    except Exception as e:
        logger.error(f"Failed to log club_product_category_unassigned for product {instance.product.name}: {str(e)}")


@receiver(post_save, sender=SyncJob)
def log_sync_job_save(sender, instance, created, **kwargs):
    """Log sync job creation and updates"""
    user = get_current_user()

    if created:
        action_type = 'club_sync_job_created'
        description = f"Created {instance.sync_type} sync job"
    else:
        # Check if status changed
        if hasattr(instance, '_old_status') and instance._old_status != instance.status:
            if instance.status == 'completed':
                action_type = f"{instance.sync_type}_sync_completed"
                description = f"{instance.sync_type.upper()} sync completed successfully"
            elif instance.status == 'failed':
                action_type = f"{instance.sync_type}_sync_failed"
                description = f"{instance.sync_type.upper()} sync failed: {instance.error_message}"
            elif instance.status == 'cancelled':
                action_type = 'club_sync_job_cancelled'
                description = f"{instance.sync_type.upper()} sync job was cancelled"
            else:
                action_type = 'club_sync_job_updated'
                description = f"Updated {instance.sync_type} sync job status to {instance.status}"
        else:
            action_type = 'club_sync_job_updated'
            description = f"Updated {instance.sync_type} sync job"

    try:
        AuditLog.log_action(
            user=user,
            action_type=action_type,
            description=description,
            sync_job_id=str(instance.id),
            sync_type=instance.sync_type,
            status=instance.status,
            progress_percentage=instance.progress_percentage,
            current_step=instance.current_step,
            clubs_created=instance.clubs_created,
            clubs_updated=instance.clubs_updated,
            categories_created=instance.categories_created,
            categories_updated=instance.categories_updated,
            products_created=instance.products_created,
            products_updated=instance.products_updated,
            error_message=instance.error_message,
            affected_model='SyncJob',
            affected_object_id=str(instance.id)
        )
        logger.info(f"Logged {action_type} for sync job {instance.id}")
    except Exception as e:
        logger.error(f"Failed to log {action_type} for sync job {instance.id}: {str(e)}")


@receiver(pre_save, sender=SyncJob)
def track_sync_job_status_change(sender, instance, **kwargs):
    """Track status changes for sync jobs"""
    if instance.pk:
        try:
            old_instance = SyncJob.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except SyncJob.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(pre_save, sender=Product)
def track_product_stock_changes(sender, instance, **kwargs):
    """Track stock status changes for products"""
    if instance.pk:
        try:
            old_instance = Product.objects.get(pk=instance.pk)
            instance._old_stock_status = old_instance.stock_status
        except Product.DoesNotExist:
            instance._old_stock_status = None
    else:
        instance._old_stock_status = None


@receiver(post_save, sender=Product)
def log_stock_status_change(sender, instance, created, **kwargs):
    """Log stock status changes for products"""
    if not created and hasattr(instance, '_old_stock_status'):
        old_status = instance._old_stock_status
        new_status = instance.stock_status

        if old_status and old_status != new_status:
            user = get_current_user()

            try:
                primary_category = instance.primary_category
                club_name = getattr(primary_category.club, 'name', '') if primary_category else ''

                AuditLog.log_action(
                    user=user,
                    action_type='club_stock_status_changed',
                    description=f"Stock status changed for {instance.name}: {old_status} → {new_status}",
                    product_id=instance.id,
                    product_name=instance.name,
                    club_name=club_name,
                    old_status=old_status,
                    new_status=new_status,
                    affected_model='Product',
                    affected_object_id=str(instance.id)
                )
                logger.info(f"Logged stock status change for product {instance.name}")
            except Exception as e:
                logger.error(f"Failed to log stock status change for product {instance.name}: {str(e)}")


@receiver(pre_save, sender=ProductVariation)
def track_variation_stock_changes(sender, instance, **kwargs):
    """Track stock quantity changes for variations"""
    if instance.pk:
        try:
            old_instance = ProductVariation.objects.get(pk=instance.pk)
            instance._old_stock_quantity = old_instance.stock_quantity
        except ProductVariation.DoesNotExist:
            instance._old_stock_quantity = None
    else:
        instance._old_stock_quantity = None


@receiver(post_save, sender=ProductVariation)
def log_variation_stock_change(sender, instance, created, **kwargs):
    """Log stock quantity changes for variations"""
    if not created and hasattr(instance, '_old_stock_quantity'):
        old_quantity = instance._old_stock_quantity
        new_quantity = instance.stock_quantity

        if old_quantity is not None and old_quantity != new_quantity:
            user = get_current_user()

            try:
                AuditLog.log_action(
                    user=user,
                    action_type='club_variation_stock_updated',
                    description=f"Stock updated for {instance.product.name} ({instance.variation_value}): {old_quantity} → {new_quantity}",
                    product_id=instance.product.id,
                    product_name=instance.product.name,
                    variation_id=instance.id,
                    variation_type=instance.variation_type,
                    variation_value=instance.variation_value,
                    old_quantity=old_quantity,
                    new_quantity=new_quantity,
                    affected_model='ProductVariation',
                    affected_object_id=str(instance.id)
                )
                logger.info(f"Logged stock change for variation {instance.variation_value}")
            except Exception as e:
                logger.error(f"Failed to log stock change for variation {instance.variation_value}: {str(e)}")