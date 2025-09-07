from functools import wraps
from flask import abort
from flask_login import current_user

def role_required(*roles):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            # CORRECTED LINE: Check the role directly from the current_user object
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403) # Forbidden
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper