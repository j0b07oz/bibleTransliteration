import os


def _env_flag(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {'1', 'true', 'yes', 'on'}


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-this-in-production')

    # Session cookie hardening. HTTPOnly and SameSite=Lax are safe defaults for
    # everyone; Secure is opt-in via env so local HTTP development still works
    # (set SESSION_COOKIE_SECURE=true in production, behind HTTPS).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _env_flag('SESSION_COOKIE_SECURE', default=False)
    # Add any other configuration variables here
