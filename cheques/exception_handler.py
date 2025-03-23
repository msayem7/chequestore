import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    # Log exception
    logger.error(
        f"Error in {context['view'].__class__.__name__}: {str(exc)}",
        exc_info=True,
        extra={'user': context['request'].user}
    )
    
    # Call default handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        response.data = {
            'error': {
                'code': response.status_code,
                'message': get_user_message(exc),
                'details': response.data
            }
        }
    else:
        response = Response(
            {'error': {
                'code': 500,
                'message': 'An unexpected error occurred'
            }},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return response

def get_user_message(exc):
    if hasattr(exc, 'get_full_details'):
        return exc.get_full_details()
    return str(exc)