import logging
import os
from logging.handlers import RotatingFileHandler
from flask import Flask, request, redirect
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config

app = Flask(__name__)

# Load configuration settings from config.py
app.config.from_object(Config)

# Honor X-Forwarded-Proto/Host from the reverse proxy so request.scheme is
# correct behind Heroku/nginx (needed for the HTTPS redirect below).
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Enable CSRF protection for all state-changing requests. Tests disable this
# via WTF_CSRF_ENABLED=False (see tests/conftest.py); the browser sends the
# token as a hidden form field or the X-CSRFToken header (see templates/JS).
csrf = CSRFProtect(app)

# Configure logging
if not app.debug and not app.testing:
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.mkdir('logs')

    # File handler with rotation
    file_handler = RotatingFileHandler(
        'logs/bible_transliteration.log',
        maxBytes=10240000,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Bible Transliteration application startup')
else:
    # Console logging for development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s'
    ))
    console_handler.setLevel(logging.DEBUG)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)

# HTTPS redirect middleware
@app.before_request
def redirect_to_https():
    """Redirect HTTP requests to HTTPS in production.

    ProxyFix (above) makes request.scheme reflect the client's original
    protocol, so this works behind a reverse proxy. Skipped in debug/testing
    so local HTTP development and the test client are unaffected.
    """
    if app.debug or app.testing:
        return
    if request.scheme == 'http':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)
