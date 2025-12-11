import logging
from aiohttp import web

from services.utils.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """Handles WebSocket connections for log streaming."""
    
    async def handle(self, request):
        """Handle WebSocket connection for strategy logs."""
        strategy_id = request.match_info['strategy_id']
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        await websocket_manager.add_connection(strategy_id, ws)
        logger.info(f"WebSocket connection established for strategy: {strategy_id}")
        
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    pass  # Handle client messages if needed
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f'WebSocket connection closed with exception {ws.exception()}')
        finally:
            websocket_manager.remove_connection(strategy_id, ws)
            logger.info(f"WebSocket connection closed for strategy: {strategy_id}")
        
        return ws
