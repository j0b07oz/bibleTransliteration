import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-this-in-production')
    # Add any other configuration variables here
