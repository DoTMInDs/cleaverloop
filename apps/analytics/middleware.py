import uuid
import threading
import logging

_correlation_local = threading.local()

def get_current_correlation_id() -> str:
    """Retrieve the current thread-local correlation ID."""
    return getattr(_correlation_local, 'correlation_id', str(uuid.uuid4()))

class CorrelationIDMiddleware:
    """
    Middleware that assigns a unique correlation ID to every incoming request
    and attaches it to response headers for end-to-end tracing.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Extract from client header or generate new UUID
        correlation_id = request.headers.get('X-Correlation-ID') or str(uuid.uuid4())
        request.correlation_id = correlation_id
        _correlation_local.correlation_id = correlation_id

        response = self.get_response(request)
        response['X-Correlation-ID'] = correlation_id
        return response
