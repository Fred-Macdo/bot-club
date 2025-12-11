import logging
from aiohttp import web


class HealthHandler:
    """Handles health check endpoints."""
    
    def __init__(self, app_state):
        self.app_state = app_state
    
    async def health_check(self, request):
        """Returns the health status of all services."""
        return web.json_response({
            "status": "healthy",
            "services": {
                "db": "connected" if self.app_state.db_client else "disconnected",
                "backtest": "running" if self.app_state.backtest_service else "stopped",
                "trading": "running" if self.app_state.trading_service else "stopped"
            }
        })
