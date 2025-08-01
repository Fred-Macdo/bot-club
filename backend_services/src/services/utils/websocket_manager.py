import asyncio
import logging
from typing import Dict, List, Any
from aiohttp import web

class WebSocketManager:
    """Manages WebSocket connections for log streaming."""
    def __init__(self):
        self.active_connections: Dict[str, List[web.WebSocketResponse]] = {}

    async def add_connection(self, strategy_id: str, ws: web.WebSocketResponse):
        """Adds a new WebSocket connection."""
        if strategy_id not in self.active_connections:
            self.active_connections[strategy_id] = []
        self.active_connections[strategy_id].append(ws)

    def remove_connection(self, strategy_id: str, ws: web.WebSocketResponse):
        """Removes a WebSocket connection."""
        if strategy_id in self.active_connections:
            self.active_connections[strategy_id].remove(ws)
            if not self.active_connections[strategy_id]:
                del self.active_connections[strategy_id]

    async def broadcast(self, strategy_id: str, message: Dict[str, Any]):
        """Broadcasts a message to all clients for a given strategy."""
        if strategy_id in self.active_connections:
            for ws in self.active_connections[strategy_id]:
                try:
                    await ws.send_json(message)
                except ConnectionResetError:
                    # Handle case where client disconnects abruptly
                    self.remove_connection(strategy_id, ws)

# Singleton instance of the WebSocketManager
websocket_manager = WebSocketManager()

class WebSocketLogHandler(logging.Handler):
    """A logging handler that sends logs over a WebSocket."""
    def __init__(self, strategy_id: str):
        super().__init__()
        self.strategy_id = strategy_id
        # Optional: If you want to format the message string itself, you can add a formatter
        # self.setFormatter(logging.Formatter('%(message)s'))

    def emit(self, record: logging.LogRecord):
        """Emits a log record to the WebSocket."""
        # The 'created' attribute is a Unix timestamp
        log_entry = {
            "timestamp": record.created * 1000, # Convert to milliseconds for JavaScript
            "level": record.levelname,
            "message": self.format(record), # Use the handler's format method
        }
        
        # Wrap the log entry in a structured message with a 'type'
        message_to_send = {
            "type": "log",
            "data": log_entry
        }
        
        # We need to run the async broadcast in the event loop
        asyncio.create_task(websocket_manager.broadcast(self.strategy_id, message_to_send)) 