"""
Backend Service Entry Point

This module initializes and runs the backend service with:
- MongoDB connection
- Backtest service
- Trading endpoints
- WebSocket support for live logs
"""
import asyncio
import logging
from aiohttp import web
from pymongo import AsyncMongoClient

from config import (
    MONGO_HOST, MONGO_PORT, MONGO_URL, MONGO_DB, LOG_LEVEL, SERVICE_PORT
)
from services.backtest.backtest_service import BacktestService
from api.routes import setup_routes
from api.trading_manager import trading_manager
from api.celery_trading_manager import celery_trading_manager


# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackendService:
    """
    Main application state container.
    Holds database connections and service references.
    """
    
    def __init__(self):
        self.app = web.Application()
        self.db_client = None
        self.db = None
        self.backtest_service = None
        self.trading_service = None
        
        # Setup routes with self as app_state
        setup_routes(self.app, self)

    async def startup(self):
        """Initialize database and services."""
        # Initialize MongoDB connection
        logger.info(f"Connecting to MongoDB at {MONGO_HOST}:{MONGO_PORT}")
        self.db_client = AsyncMongoClient(MONGO_URL)
        self.db = self.db_client[MONGO_DB]
        logger.info(f"Connected to MongoDB at {MONGO_HOST}:{MONGO_PORT}")
        
        # Initialize backtest service
        logger.info("Initializing backtest service")
        self.backtest_service = BacktestService(self.db)
        await self.backtest_service.initialize()

        logger.info("Backend service started successfully")

    async def cleanup(self):
        """Cleanup resources on shutdown."""
        logger.info("Shutting down services...")
        
        # Stop all running traders
        await celery_trading_manager.stop_all()
        
        # Shutdown backtest service
        if self.backtest_service:
            await self.backtest_service.shutdown()
        
        # Close database connection
        if self.db_client:
            self.db_client.close()
            logger.info("Database connection closed")


async def main():
    """Application entry point."""
    service = BackendService()
    
    await service.startup()
    
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