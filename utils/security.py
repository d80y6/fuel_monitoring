"""
Security middleware for the Flask application.

Adds standard security headers to every response and optionally forces HTTPS.
"""
import logging
from flask import request, redirect, current_app
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def init_security_middleware(app):
    """Register *after_request* and *before_request* hooks on *app*."""

    @app.after_request
    def set_security_headers(response):
        """Attach best-practice security headers to every response."""
        # Content-Security-Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://unpkg.com https://code.jquery.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data:; "
            "font-src 'self' https://cdnjs.cloudflare.com; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers['Content-Security-Policy'] = csp

        # Prevent MIME sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'

        # Prevent clickjacking
        response.headers['X-Frame-Options'] = 'DENY'

        # XSS filter (legacy browsers)
        response.headers['X-XSS-Protection'] = '1; mode=block'

        # Referrer policy — send origin only on cross-origin requests
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions policy — disable optional browser features
        response.headers['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=(), payment=()'
        )

        # Strict-Transport-Security — only when the request was served over TLS
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains; preload'
            )

        # Remove server identification
        response.headers.pop('Server', None)

        return response

    @app.before_request
    def force_https():
        """Redirect HTTP to HTTPS when PREFERRED_URL_SCHEME is https."""
        if current_app.config.get('FORCE_HTTPS') and not request.is_secure:
            url = request.url.replace('http://', 'https://', 1)
            return redirect(url, code=301)

    logger.info("Security middleware registered")
