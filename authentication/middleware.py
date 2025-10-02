import logging
from django.utils import timezone
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from .models import UserSession, AuditLog

logger = logging.getLogger(__name__)


class AuthenticationMiddleware:
    """
    Middleware for enhanced authentication features including:
    - Session tracking
    - Audit logging
    - IP tracking
    - Automatic logout on role changes
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process request before view
        self.process_request(request)

        response = self.get_response(request)

        # Process response after view
        self.process_response(request, response)

        return response

    def process_request(self, request):
        """Process incoming request"""
        if request.user.is_authenticated:
            # Update user's last login IP
            current_ip = self.get_client_ip(request)
            if request.user.last_login_ip != current_ip:
                request.user.last_login_ip = current_ip
                request.user.save(update_fields=['last_login_ip'])

            # Track or update user session
            self.track_user_session(request)

            # Check if user is still active
            if not request.user.is_active:
                logout(request)
                return redirect('authentication:login')

            # Check if sales rep is still active
            if request.user.is_sales_rep and not request.user.is_active_sales_rep:
                logout(request)
                return redirect('authentication:login')

    def process_response(self, request, response):
        """Process outgoing response"""
        if request.user.is_authenticated:
            # Update session activity
            self.update_session_activity(request)

        return response

    def track_user_session(self, request):
        """Track or update user session"""
        try:
            session_key = request.session.session_key
            if not session_key:
                return

            user_session, created = UserSession.objects.get_or_create(
                session_key=session_key,
                defaults={
                    'user': request.user,
                    'ip_address': self.get_client_ip(request),
                    'user_agent': request.META.get('HTTP_USER_AGENT', '')[:1000],  # Limit length
                }
            )

            if created:
                # Log new session creation
                AuditLog.log_action(
                    user=request.user,
                    action_type='login',
                    description=f'User logged in from {user_session.ip_address}',
                    request=request,
                    session_id=session_key
                )

        except Exception as e:
            logger.error(f"Error tracking user session: {e}")

    def update_session_activity(self, request):
        """Update session last activity"""
        try:
            session_key = request.session.session_key
            if session_key:
                UserSession.objects.filter(
                    session_key=session_key,
                    user=request.user
                ).update(last_activity=timezone.now())

        except Exception as e:
            logger.error(f"Error updating session activity: {e}")

    @staticmethod
    def get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')

        return ip


class RoleBasedAccessMiddleware:
    """
    Middleware to automatically redirect users based on their roles
    and restrict access to certain URLs
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Define role-based URL patterns
        self.admin_only_paths = [
            '/admin/',
            '/auth/users/',
            '/auth/assignments/',
            '/auth/audit-logs/',
        ]

        self.sales_rep_restricted_paths = [
            '/admin/',
            '/auth/users/create/',
            '/auth/assignments/bulk/',
        ]

        # Public paths that don't require authentication
        self.public_paths = [
            '/',  # Frontend landing page
            '/auth/login/',
            '/auth/logout/',
            '/auth/signup/',  # Customer signup
            '/accounts/',  # Django built-in auth URLs (password reset, etc.)
            '/static/',
            '/media/',
            '/frontend/',  # Frontend static files
        ]

    def __call__(self, request):
        # Check access before view processing
        redirect_response = self.check_access(request)
        if redirect_response:
            return redirect_response

        response = self.get_response(request)
        return response

    def check_access(self, request):
        """Check if user has access to the requested path"""
        path = request.path

        # Allow public paths
        if any(path.startswith(public_path) for public_path in self.public_paths):
            return None

        # Require authentication for all other paths
        if not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")

        # Check admin-only paths
        if any(path.startswith(admin_path) for admin_path in self.admin_only_paths):
            if not request.user.is_admin:
                AuditLog.log_action(
                    user=request.user,
                    action_type='permission_denied',
                    description=f'Attempted to access admin-only path: {path}',
                    request=request,
                    attempted_path=path
                )
                return redirect('authentication:access-denied')

        # Check sales rep restrictions
        if any(path.startswith(restricted_path) for restricted_path in self.sales_rep_restricted_paths):
            if request.user.is_sales_rep:
                AuditLog.log_action(
                    user=request.user,
                    action_type='permission_denied',
                    description=f'Sales rep attempted to access restricted path: {path}',
                    request=request,
                    attempted_path=path
                )
                return redirect('authentication:access-denied')

        return None


class AuditLoggingMiddleware:
    """
    Middleware to automatically log important user actions
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # Define actions to log
        self.logged_actions = {
            'POST': [
                'user_created', 'assignment_created', 'data_modified'
            ],
            'PUT': [
                'user_updated', 'assignment_updated', 'data_modified'
            ],
            'PATCH': [
                'user_updated', 'assignment_updated', 'data_modified'
            ],
            'DELETE': [
                'user_deleted', 'assignment_deleted', 'data_deleted'
            ]
        }

        # Paths to monitor for automatic logging
        self.monitored_paths = [
            '/auth/users/',
            '/auth/assignments/',
            '/clubs/',
            '/schools/',
        ]

    def __call__(self, request):
        response = self.get_response(request)

        # Log actions after successful requests
        if request.user.is_authenticated and response.status_code < 400:
            self.log_user_action(request, response)

        return response

    def log_user_action(self, request, response):
        """Log user actions based on request method and path"""
        try:
            path = request.path
            method = request.method

            # Check if this path should be monitored
            if not any(path.startswith(monitored_path) for monitored_path in self.monitored_paths):
                return

            # Determine action type based on method and path
            action_type = self.determine_action_type(method, path)
            if not action_type:
                return

            # Create description
            description = self.create_action_description(method, path, request)

            # Log the action
            AuditLog.log_action(
                user=request.user,
                action_type=action_type,
                description=description,
                request=request,
                request_method=method,
                request_path=path,
                response_status=response.status_code
            )

        except Exception as e:
            logger.error(f"Error in audit logging middleware: {e}")

    def determine_action_type(self, method, path):
        """Determine action type based on HTTP method and path"""
        if method == 'POST':
            if '/users/' in path:
                return 'user_created'
            elif '/assignments/' in path:
                return 'assignment_created'
            else:
                return 'data_access'

        elif method in ['PUT', 'PATCH']:
            if '/users/' in path:
                return 'user_updated'
            elif '/assignments/' in path:
                return 'assignment_updated'
            else:
                return 'data_access'

        elif method == 'DELETE':
            if '/users/' in path:
                return 'user_deleted'
            elif '/assignments/' in path:
                return 'assignment_deleted'
            else:
                return 'data_deleted'

        elif method == 'GET':
            return 'data_access'

        return None

    def create_action_description(self, method, path, request):
        """Create human-readable action description"""
        action_map = {
            'GET': 'accessed',
            'POST': 'created',
            'PUT': 'updated',
            'PATCH': 'modified',
            'DELETE': 'deleted'
        }

        action = action_map.get(method, 'performed action on')
        return f"User {action} {path}"


class SessionSecurityMiddleware:
    """
    Middleware to enhance session security
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Check for session hijacking (IP change)
            self.check_session_security(request)

        response = self.get_response(request)
        return response

    def check_session_security(self, request):
        """Check for potential session security issues"""
        try:
            session_key = request.session.session_key
            if not session_key:
                return

            current_ip = AuthenticationMiddleware.get_client_ip(request)
            current_user_agent = request.META.get('HTTP_USER_AGENT', '')

            # Get the session record
            try:
                user_session = UserSession.objects.get(
                    session_key=session_key,
                    user=request.user,
                    is_active=True
                )

                # Check for IP changes (potential session hijacking)
                if user_session.ip_address != current_ip:
                    AuditLog.log_action(
                        user=request.user,
                        action_type='security_alert',
                        description=f'Session IP changed from {user_session.ip_address} to {current_ip}',
                        request=request,
                        old_ip=user_session.ip_address,
                        new_ip=current_ip,
                        session_id=session_key
                    )

                    # Optionally logout user for security
                    # logout(request)
                    # return redirect('authentication:login')

                # Check for user agent changes
                if user_session.user_agent != current_user_agent:
                    AuditLog.log_action(
                        user=request.user,
                        action_type='security_alert',
                        description='Session user agent changed',
                        request=request,
                        session_id=session_key
                    )

            except UserSession.DoesNotExist:
                # Session not found, might be a security issue
                AuditLog.log_action(
                    user=request.user,
                    action_type='security_alert',
                    description='Active session not found in database',
                    request=request,
                    session_id=session_key
                )

        except Exception as e:
            logger.error(f"Error in session security middleware: {e}")


class AutoLogoutMiddleware:
    """
    Middleware to automatically logout inactive users
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, 'AUTO_LOGOUT_TIMEOUT', 3600)  # 1 hour default

    def __call__(self, request):
        if request.user.is_authenticated:
            if self.should_auto_logout(request):
                AuditLog.log_action(
                    user=request.user,
                    action_type='logout',
                    description='Automatic logout due to inactivity',
                    request=request
                )
                logout(request)
                return redirect('authentication:login')

        response = self.get_response(request)
        return response

    def should_auto_logout(self, request):
        """Check if user should be automatically logged out"""
        try:
            session_key = request.session.session_key
            if not session_key:
                return False

            user_session = UserSession.objects.get(
                session_key=session_key,
                user=request.user,
                is_active=True
            )

            # Check if session has been inactive for too long
            time_since_activity = timezone.now() - user_session.last_activity
            return time_since_activity.total_seconds() > self.timeout

        except UserSession.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error checking auto logout: {e}")
            return False