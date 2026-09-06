"""
Internationalization support for the Fuel Tank Monitoring System
"""
from flask import request, session
from flask_babel import Babel

babel = Babel()

def get_locale():
    """
    Determine the best language for the user.
    Priority: URL parameter > session > browser preference > default (en)
    """
    # First check if there's a language parameter in the URL
    lang = request.args.get('lang')
    if lang in ['en', 'ar']:
        session['lang'] = lang
        return lang
    
    # Then check if there's a language set in the session
    if 'lang' in session and session['lang'] in ['en', 'ar']:
        return session['lang']
    
    # Otherwise, use browser's preferred language
    return request.accept_languages.best_match(['en', 'ar'], default='en')

def init_app(app):
    """Initialize internationalization support"""
    babel.init_app(app, locale_selector=get_locale)
    app.config['BABEL_DEFAULT_LOCALE'] = 'en'
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'