import logging
from aiohttp import web

logger = logging.getLogger(__name__)


@web.middleware
async def error_middleware(request, handler):
    """Global error handling middleware."""
    try:
        return await handler(request)
    except Exception as e:
        logger.error(f"Middleware: Error processing request: {str(e)}", exc_info=True)
        return web.json_response(
            {"error": str(e)}, 
            status=500
        )
