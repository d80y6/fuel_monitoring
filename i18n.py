"""
Internationalization module for the Fuel Tank Monitoring System

This module provides multi-language support using Flask-Babel.
"""
from flask import request, session, g, redirect
from flask_babel import Babel

babel = Babel()

def get_locale():
    """
    Determine the best language to use based on user preference.
    Order of precedence:
    1. Language stored in session
    2. Language from browser request
    3. Default to English
    """
    # First check if user has a language preference in the session
    if 'language' in session:
        return session['language']
    
    # Otherwise, try to detect from the browser's Accept-Language header
    return request.accept_languages.best_match(['en', 'ar']) or 'en'

def init_app(app):
    """Initialize Babel with the Flask application"""
    babel.init_app(app, locale_selector=get_locale)
    
    # Add language switching route
    @app.route('/set_language/<language>')
    def set_language(language):
        """Set the user's language preference"""
        # Validate language
        if language not in ['en', 'ar']:
            language = 'en'
        
        # Store in session
        session['language'] = language
        
        # Redirect back to the previous page or home
        return redirect(request.referrer or '/')
    
    # Make language available in templates
    @app.context_processor
    def inject_language():
        return {'current_language': get_locale()}