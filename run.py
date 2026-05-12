#!/usr/bin/env python3
"""
Application entry point for development server.
For production, use gunicorn with wsgi.py
"""
from app import create_app
from app.models import db
import os

app = create_app(os.environ.get('FLASK_ENV', 'development'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)