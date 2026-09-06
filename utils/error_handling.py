def handle_errors(logger, default_return=None):
    """Decorator to handle errors and log them."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {str(e)}")
                return default_return
        return wrapper
    return decorator