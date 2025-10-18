import asyncio
import logging
from aiohttp import web
import json
from motor.motor_asyncio import AsyncIOMotorClient
from lumibot.brokers import Alpaca
from lumibot.traders import Trader
from bson import ObjectId
import logging
import multiprocessing as mp
from logging.handlers import QueueHandler
import asyncio

# Local imports
from config import (
    MONGO_HOST, MONGO_PORT, MONGO_URL, MONGO_DB, LOG_LEVEL,
    SERVICE_PORT
)
from services.backtest.backtest_service import BacktestService
from services.trading.trading_service import CryptoStrategy
from services.utils.enums import TradingMode
from services.utils.websocket_manager import websocket_manager, WebSocketLogHandler
from models.user_config import ConfigEncryption
from models.strategy import StrategyConfig


# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_strategy_process(strategy_config, alpaca_config, log_queue):
    """
    This function runs in a separate process to execute the trading strategy.
    """
    try:
        # Create broker and strategy
        broker = Alpaca(config=alpaca_config)
        strategy = CryptoStrategy(broker=broker, strategy_config=strategy_config)

        # Configure logging to pass logs back to the main process
        queue_handler = QueueHandler(log_queue)
        
        # The strategy logger is a LoggerAdapter, so we need to add the handler
        # to the underlying logger instance.
        underlying_logger = strategy.logger.logger
        underlying_logger.addHandler(queue_handler)
        underlying_logger.setLevel(logging.INFO)
        
        # Run the strategy
        strategy.run_live()
    except Exception as e:
        # Log any exceptions that occur during strategy execution
        # Create a basic logger to put the error in the queue
        temp_logger = logging.getLogger('process_runner')
        temp_logger.addHandler(QueueHandler(log_queue))
        temp_logger.setLevel(logging.ERROR)
        temp_logger.error(f"Error in strategy process: {e}", exc_info=True)


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
        self.trading_service = None
        self.executor = None # Will be initialized in startup
        self.running_traders = {} # To keep track of running processes
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
        
        # WebSocket endpoint for logs
        self.app.router.add_get('/ws/trading/{strategy_id}', self.websocket_handler)
        
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

    async def websocket_handler(self, request):
        """
        Handles WebSocket connections for log streaming.
        Args:
            request: The request object
        Returns:
            The WebSocket response
        """
        strategy_id = request.match_info['strategy_id']
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        await websocket_manager.add_connection(strategy_id, ws)
        logger.info(f"WebSocket connection established for strategy: {strategy_id}")
        
        return ws
        
    async def health_check(self, request):
        """
        Handles health check requests.
        Args:
            request: The request object
        Returns:
            The health check response
        """
        return web.json_response({
            "status": "healthy",
            "services": {
                "db": "connected" if self.db_client else "disconnected",
                "backtest": "running" if self.backtest_service else "stopped",
                "trading": "running" if self.trading_service else "stopped"
            }
        })

    async def run_backtest(self, request):
        """
        Handles backtest requests.
        Args:
            request: The request object
        Returns:
            The backtest response
        """
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
        """
        Handles trading requests.
        Args:
            request: The request object
        Returns:
            The trading response
        """
        logger.info("Received request for /trading/run")
        try:
            data = await request.json()
            logger.info(f"Received trading request data: {data}")
            
            required_fields = ['strategy_id', 'mode', 'user_id', 'data_provider']
            for field in required_fields:
                if field not in data:
                    logger.error(f"Missing required field: {field}")
                    return web.json_response({"error": f"Missing required field: {field}"}, status=400)

            logger.info(f"All required fields present. Starting trading session for strategy: {data['strategy_id']}")
            
            strategy_id = data['strategy_id']
            user_id = data['user_id']
            mode = TradingMode(data['mode'])
            data_provider = data['data_provider']

            # 1. Fetch user credentials from MongoDB
            user_config = await self.db.user_config.find_one({"user_id": user_id})
            if not user_config:
                return web.json_response({"error": "User configuration not found"}, status=404)

            # 2. Decrypt credentials and configure Alpaca
            if mode == TradingMode.PAPER:
                api_key = ConfigEncryption.decrypt_value(user_config.get("alpaca_paper_api_key"))
                secret_key = ConfigEncryption.decrypt_value(user_config.get("alpaca_paper_secret_key"))
                paper = True
                logger.info(f"Main Service: Using Alpaca Paper API key: {api_key}")
            else: # Live trading
                api_key = ConfigEncryption.decrypt_value(user_config.get("alpaca_live_api_key"))
                secret_key = ConfigEncryption.decrypt_value(user_config.get("alpaca_live_secret_key"))
                paper = False
            
            if not api_key or not secret_key:
                return web.json_response({"error": "Alpaca API key/secret not configured for the selected mode"}, status=400)

            ALPACA_CONFIG = {
                "API_KEY": api_key,
                "API_SECRET": secret_key,
                "PAPER": paper,
            }
            # get strategy config from database
            strategy_config = await self.db.strategy.find_one({"_id": ObjectId(strategy_id)})

            logger.info(f"Main Service: Strategy configuration found: {strategy_config}, type: {type(strategy_config)}")

            if not strategy_config:
                return web.json_response({"error": "Strategy configuration not found"}, status=404)
            
            # Use multiprocessing to run the strategy in a separate process
            log_queue = mp.Queue()
            process = mp.Process(
                target=run_strategy_process,
                args=(strategy_config, ALPACA_CONFIG, log_queue)
            )
            process.start()

            # Start a listener task to forward logs from the queue to the websocket
            log_listener_task = asyncio.create_task(self.log_listener(strategy_id, log_queue))

            self.running_traders[strategy_id] = {
                "process": process,
                "log_queue": log_queue,
                "log_listener_task": log_listener_task
            }

            logger.info(f"Trading process started for strategy: {strategy_id} with PID {process.pid}")
            return web.json_response({
                "status": "trading_started",
                "strategy_id": strategy_id
            })
            
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON from request body.")
            return web.json_response({"error": "Invalid JSON format"}, status=400)
        except Exception as e:
            logger.error(f"An unexpected error occurred in run_trading: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def log_listener(self, strategy_id: str, log_queue: mp.Queue):
        """Listens for log records from a strategy process and forwards them."""
        loop = asyncio.get_running_loop()
        while True:
            try:
                # Use run_in_executor to wait for items from the sync queue without blocking
                log_record = await loop.run_in_executor(None, log_queue.get)
                if log_record is None:  # Sentinel value to stop
                    break
                
                log_message = f"{log_record.asctime} | {log_record.levelname} | [{log_record.name}] {log_record.getMessage()}"
                await websocket_manager.broadcast_to_strategy(strategy_id, log_message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in log listener for {strategy_id}: {e}")
        logger.info(f"Log listener for strategy {strategy_id} stopped.")

    async def stop_trading(self, request):
        """Stop live/paper trading"""
        try:
            data = await request.json()
            strategy_id = data.get('strategy_id')

            if not strategy_id:
                return web.json_response({"error": "Strategy ID required"}, status=400)

            trader_info = self.running_traders.get(strategy_id)
            if not trader_info or not trader_info["process"].is_alive():
                return web.json_response({"error": "Trader not running or not found"}, status=404)

            # Terminate the process
            trader_info["process"].terminate()
            trader_info["process"].join(timeout=5)
            logger.info(f"Terminated process for strategy {strategy_id}")

            # Stop the log listener
            trader_info["log_queue"].put(None) # Send sentinel
            trader_info["log_listener_task"].cancel()

            del self.running_traders[strategy_id]

            return web.json_response({"status": "stopped", "strategy_id": strategy_id})

        except Exception as e:
            logger.error(f"Error stopping trading: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def get_trading_status(self, request):
        """Get trading status"""
        try:
            strategy_id = request.match_info['strategy_id']
            result = self.trading_service.get_trading_session_status(strategy_id)
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
        # Stop all running traders
        for strategy_id in list(self.running_traders.keys()):
            trader_info = self.running_traders[strategy_id]
            logger.info(f"Stopping trader for strategy {strategy_id}...")
            if trader_info["process"].is_alive():
                trader_info["process"].terminate()
                trader_info["process"].join(timeout=5)
            trader_info["log_queue"].put(None)
            trader_info["log_listener_task"].cancel()

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