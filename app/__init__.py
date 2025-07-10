from flask import Flask, request, redirect
from config import Config

app = Flask(__name__)

# Load configuration settings from config.py
app.config.from_object(Config)
