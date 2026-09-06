"""
Custom translation loader for the Fuel Tank Monitoring System
"""
import os
import json
from flask import request, session, g

# Dictionary to store translations
translations = {
    'en': {},
    'ar': {}
}

def load_translations():
    """Load translations from JSON files"""
    for lang in ['en', 'ar']:
        try:
            with open(f'translations/{lang}/LC_MESSAGES/messages.json', 'r', encoding='utf-8') as f:
                translations[lang] = json.load(f)
            print(f"Loaded {len(translations[lang])} translations for {lang}")
        except FileNotFoundError:
            print(f"Warning: Translation file for {lang} not found")
        except json.JSONDecodeError:
            print(f"Warning: Translation file for {lang} is not valid JSON")

def get_locale():
    """Get the current locale from session or request"""
    # First check if user has a language preference in the session
    if 'language' in session:
        return session['language']
    
    # Otherwise, try to detect from the browser's Accept-Language header
    return request.accept_languages.best_match(['en', 'ar']) or 'en'

def gettext(message, **variables):
    """
    Translate a message with variable substitution
    
    Args:
        message: The message to translate
        **variables: Variables to substitute in the translated message
    
    Returns:
        Translated message with variables substituted
    """
    locale = get_locale()
    
    # Get the translated message
    if locale in translations and message in translations[locale]:
        translated = translations[locale][message]
    else:
        translated = message
    
    # Substitute variables if any
    if variables:
        try:
            return translated % variables
        except:
            # If substitution fails, return the message as is
            return translated
    
    return translated

# Create an alias for gettext
_ = gettext

def init_app(app):
    """Initialize the translation module with the Flask application"""
    # Load translations
    load_translations()
    
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
        return request.referrer or '/'
    
    # Make language available in templates
    @app.context_processor
    def inject_language():
        return {
            'current_language': get_locale(),
            '_': gettext  # Make translation function available in templates
        }