import logging
from aiohttp import web

logger = logging.getLogger(__name__)


class BacktestHandler:
    """Handles backtest-related endpoints."""
    
    def __init__(self, app_state):
        self.app_state = app_state
    
    async def run_backtest(self, request):
        """Start a new backtest."""
        try:
            data = await request.json()
            logger.info(f"Received backtest request: {data}")
            
            required_fields = ['strategy_id', 'user_id', 'initial_capital', 'start_date', 'end_date', 'timeframe']
            for field in required_fields:
                if field not in data:
                    return web.json_response({"error": f"Missing required field: {field}"}, status=400)
            
            backtest_id = await self.app_state.backtest_service.run_backtest(
                strategy_id=data['strategy_id'],
                user_id=data['user_id'],
                params=data
            )
            
            return web.json_response({
                "status": "started",
                "backtest_id": backtest_id
            })
        except Exception as e:
            logger.error(f"Error starting backtest: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def get_status(self, request):
        """Get backtest status."""
        backtest_id = request.match_info['backtest_id']
        status = await self.app_state.backtest_service.get_status(backtest_id)
        if not status:
            return web.json_response({"error": "Backtest not found"}, status=404)
        return web.json_response(status)
    
    async def cancel_backtest(self, request):
        """Cancel a running backtest."""
        backtest_id = request.match_info['backtest_id']
        success = await self.app_state.backtest_service.cancel_backtest(backtest_id)
        if not success:
            return web.json_response({"error": "Failed to cancel backtest"}, status=400)
        return web.json_response({"status": "cancelled"})
