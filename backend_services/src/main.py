import asyncio
import logging
from aiohttp import web
import json
from motor.motor_asyncio import AsyncIOMotorClient

# Local imports
from config import (
    MONGO_HOST, MONGO_PORT, MONGO_URL, MONGO_DB, LOG_LEVEL,
    SERVICE_PORT
)
from services.backtest.backtest_service import BacktestService
from services.backtest.backtest_engine import TradingMode

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BackendService:
    """
    This class is responsible for setting up the backend service and handling requests.
    It is responsible for:
    - Setting up the routes
    - Setting up the middleware
    - Setting up the services
    - Setting up the database
    """
    def __init__(self):
        self.app = web.Application()
        self.db_client = None
        self.db = None
        self.backtest_service = None
        self.setup_routes()

    def setup_routes(self):
        # Health check endpoint
        self.app.router.add_get('/health', self.health_check)
        
        # Backtest related endpoints
        self.app.router.add_post('/backtest/run', self.run_backtest)
        self.app.router.add_get('/backtest/{backtest_id}/status', self.get_backtest_status)
        self.app.router.add_delete('/backtest/{backtest_id}', self.cancel_backtest)
        
        # Trading execution endpoints
        self.app.router.add_post('/trading/run', self.run_trading)
        self.app.router.add_post('/trading/stop', self.stop_trading)
        self.app.router.add_get('/trading/status/{strategy_id}', self.get_trading_status)
        
        # Setup middleware
        self.app.middlewares.append(self.error_middleware)

    @web.middleware
    async def error_middleware(self, request, handler):
        try:
            return await handler(request)
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}", exc_info=True)
            return web.json_response(
                {"error": str(e)}, 
                status=500
            )

    async def health_check(self, request):
        return web.json_response({
            "status": "healthy",
            "services": {
                "db": "connected" if self.db_client else "disconnected",
                "backtest": "running" if self.backtest_service else "stopped"
            }
        })

    async def run_backtest(self, request):
        try:
            data = await request.json()
            logger.info(f"Received backtest request: {data}")
            
            # Validate required fields
            required_fields = ['strategy_id', 'user_id', 'initial_capital', 'start_date', 'end_date', 'timeframe']
            for field in required_fields:
                if field not in data:
                    return web.json_response({"error": f"Missing required field: {field}"}, status=400)
            
            # The user_id is passed in the payload from the main backend service
            user_id = data['user_id']
            
            # Run the backtest
            backtest_id = await self.backtest_service.start_backtest(
                strategy_id=data['strategy_id'],
                user_id=user_id, 
                params=data
            )
            
            return web.json_response({
                "status": "started",
                "backtest_id": backtest_id
            })
        except Exception as e:
            logger.error(f"Error starting backtest: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def run_trading(self, request):
        """Start trading (backtest, paper, or live)"""
        try:
            data = await request.json()
            logger.info(f"Received trading request: {data}")
            
            # Validate required fields
            required_fields = ['strategy_id', 'mode', 'user_id']
            for field in required_fields:
                if field not in data:
                    return web.json_response({"error": f"Missing required field: {field}"}, status=400)
            
            strategy_id = data['strategy_id']
            mode = TradingMode(data['mode'])
            user_id = data['user_id']
            
            if mode == TradingMode.BACKTEST:
                if 'backtest_params' not in data:
                    return web.json_response({"error": "Backtest parameters required"}, status=400)
                result = await self.backtest_service.run_trading(
                    strategy_id=strategy_id,
                    mode=mode,
                    user_id=user_id,
                    backtest_params=data['backtest_params']
                )
            else:
                if 'alpaca_config' not in data:
                    return web.json_response({"error": "Alpaca configuration required"}, status=400)
                result = await self.backtest_service.run_trading(
                    strategy_id=strategy_id,
                    mode=mode,
                    user_id=user_id,
                    alpaca_config=data['alpaca_config']
                )
            
            return web.json_response(result)
            
        except Exception as e:
            logger.error(f"Error running trading: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def stop_trading(self, request):
        """Stop live/paper trading"""
        try:
            data = await request.json()
            strategy_id = data.get('strategy_id')
            
            if not strategy_id:
                return web.json_response({"error": "Strategy ID required"}, status=400)
            
            result = await self.backtest_service.stop_trading(strategy_id)
            return web.json_response(result)
            
        except Exception as e:
            logger.error(f"Error stopping trading: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def get_trading_status(self, request):
        """Get trading status"""
        try:
            strategy_id = request.match_info['strategy_id']
            result = await self.backtest_service.get_trading_status(strategy_id)
            return web.json_response(result)
            
        except Exception as e:
            logger.error(f"Error getting trading status: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def get_backtest_status(self, request):
        backtest_id = request.match_info['backtest_id']
        status = await self.backtest_service.get_status(backtest_id)
        if not status:
            return web.json_response({"error": "Backtest not found"}, status=404)
        return web.json_response(status)

    async def cancel_backtest(self, request):
        backtest_id = request.match_info['backtest_id']
        success = await self.backtest_service.cancel_backtest(backtest_id)
        if not success:
            return web.json_response({"error": "Failed to cancel backtest"}, status=400)
        return web.json_response({"status": "cancelled"})

    async def startup(self):
        # Initialize MongoDB connection
        logger.info(f"Connecting to MongoDB at {MONGO_HOST}:{MONGO_PORT}")
        self.db_client = AsyncIOMotorClient(MONGO_URL)
        self.db = self.db_client[MONGO_DB]
        logger.info(f"Connected to MongoDB at {MONGO_HOST}:{MONGO_PORT}")
        # Initialize services
        logger.info("Initializing backtest service")
        self.backtest_service = BacktestService(self.db)
        await self.backtest_service.initialize()
        
        logger.info("Backend service started successfully")

    async def cleanup(self):
        logger.info("Shutting down services...")
        if self.backtest_service:
            await self.backtest_service.shutdown()
        
        if self.db_client:
            self.db_client.close()
            logger.info("Database connection closed")

async def main():
    service = BackendService()
    
    # Setup the service
    await service.startup()
    
    # Start the web server
    runner = web.AppRunner(service.app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', SERVICE_PORT)
    
    try:
        logger.info(f"Starting backend service on port {SERVICE_PORT}")
        await site.start()
        
        # Keep the service running
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down...")
    finally:
        await service.cleanup()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())