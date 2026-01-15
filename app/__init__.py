import logging
import os
from logging.handlers import RotatingFileHandler
from flask import Flask, request, redirect
from config import Config

app = Flask(__name__)

# Load configuration settings from config.py
app.config.from_object(Config)

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
    """Redirect HTTP requests to HTTPS in production."""
    # temporarily commenting out to check logic
    # if not app.debug:
        # Check if the request came through HTTP via reverse proxy
    #    if request.headers.get('X-Forwarded-Proto') == 'http':
    #        url = request.url.replace('http://', 'https://', 1)
    #        return redirect(url, code=301)
