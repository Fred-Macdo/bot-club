import json
import logging
from aiohttp import web
from bson import ObjectId

from services.utils.enums import TradingMode
from models.user_config import ConfigEncryption
from api.celery_trading_manager import celery_trading_manager

logger = logging.getLogger(__name__)


class TradingHandler:
    """Handles trading-related endpoints."""
    
    def __init__(self, app_state):
        self.app_state = app_state
    
    async def run_trading(self, request):
        """Start a live/paper trading session."""
        logger.info("Received request for /trading/run")
        try:
            data = await request.json()
            logger.info(f"Received trading request data: {data}")
            
            # Validate required fields
            required_fields = ['strategy_id', 'mode', 'user_id', 'data_provider']
            for field in required_fields:
                if field not in data:
                    logger.error(f"Missing required field: {field}")
                    return web.json_response({"error": f"Missing required field: {field}"}, status=400)

            strategy_id = data['strategy_id']
            user_id = data['user_id']
            
            # Check if already running
            if celery_trading_manager.is_running(strategy_id):
                return web.json_response({"error": "Strategy is already running"}, status=400)
            
            mode = TradingMode(data['mode'])

            # Fetch user credentials
            user_config = await self.app_state.db.user_config.find_one({"user_id": user_id})
            if not user_config:
                return web.json_response({"error": "User configuration not found"}, status=404)

            # Decrypt credentials and configure Alpaca
            if mode == TradingMode.PAPER:
                api_key = ConfigEncryption.decrypt_value(user_config.get("alpaca_paper_api_key"))
                secret_key = ConfigEncryption.decrypt_value(user_config.get("alpaca_paper_secret_key"))
                paper = True
                logger.info("Using Alpaca Paper Trading")
            else:
                api_key = ConfigEncryption.decrypt_value(user_config.get("alpaca_live_api_key"))
                secret_key = ConfigEncryption.decrypt_value(user_config.get("alpaca_live_secret_key"))
                paper = False
            
            if not api_key or not secret_key:
                return web.json_response({"error": "Alpaca API key/secret not configured for the selected mode"}, status=400)

            alpaca_config = {
                "API_KEY": api_key,
                "API_SECRET": secret_key,
                "PAPER": paper,
            }
            
            # Get strategy config from database
            strategy_config = await self.app_state.db.strategy.find_one({"_id": ObjectId(strategy_id)})
            if not strategy_config:
                return web.json_response({"error": "Strategy configuration not found"}, status=404)
            
            # Convert ObjectId to string for JSON serialization
            strategy_config['_id'] = str(strategy_config['_id'])
            if 'user_id' in strategy_config and isinstance(strategy_config['user_id'], ObjectId):
                strategy_config['user_id'] = str(strategy_config['user_id'])
            
            logger.info(f"Strategy configuration found: {strategy_config}")
            
            # Start the strategy
            success = await celery_trading_manager.start_strategy(
                strategy_id=strategy_id,
                strategy_config=strategy_config,
                alpaca_config=alpaca_config,
                user_id=user_id
            )
            
            if not success:
                return web.json_response({"error": "Failed to start strategy"}, status=500)
            
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
    
    async def stop_trading(self, request):
        """Stop a running trading session."""
        try:
            data = await request.json()
            strategy_id = data.get('strategy_id')

            if not strategy_id:
                return web.json_response({"error": "Strategy ID required"}, status=400)

            success = await celery_trading_manager.stop_strategy(strategy_id)
            if not success:
                return web.json_response({"error": "Trader not running or not found"}, status=404)

            return web.json_response({"status": "stopped", "strategy_id": strategy_id})

        except Exception as e:
            logger.error(f"Error stopping trading: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def get_status(self, request):
        """Get trading status for a specific strategy."""
        try:
            strategy_id = request.match_info['strategy_id']
            status = celery_trading_manager.get_status(strategy_id)
            return web.json_response(status)
        except Exception as e:
            logger.error(f"Error getting trading status: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
