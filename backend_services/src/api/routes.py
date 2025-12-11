"""
Route registration for the backend service.
"""
from aiohttp import web

from .handlers import HealthHandler, BacktestHandler, TradingHandler, WebSocketHandler
from .middleware import error_middleware


def setup_routes(app: web.Application, app_state):
    """
    Register all routes with the application.
    
    Args:
        app: The aiohttp Application
        app_state: The BackendService instance containing db, services, etc.
    """
    # Initialize handlers
    health_handler = HealthHandler(app_state)
    backtest_handler = BacktestHandler(app_state)
    trading_handler = TradingHandler(app_state)
    websocket_handler = WebSocketHandler()
    
    # Health check
    app.router.add_get('/health', health_handler.health_check)
    
    # Backtest endpoints
    app.router.add_post('/backtest/run', backtest_handler.run_backtest)
    app.router.add_get('/backtest/{backtest_id}/status', backtest_handler.get_status)
    app.router.add_delete('/backtest/{backtest_id}', backtest_handler.cancel_backtest)
    
    # Trading endpoints
    app.router.add_post('/trading/run', trading_handler.run_trading)
    app.router.add_post('/trading/stop', trading_handler.stop_trading)
    app.router.add_get('/trading/status/{strategy_id}', trading_handler.get_status)
    
    # WebSocket endpoint
    app.router.add_get('/ws/trading/{strategy_id}', websocket_handler.handle)
    
    # Middleware
    app.middlewares.append(error_middleware)
