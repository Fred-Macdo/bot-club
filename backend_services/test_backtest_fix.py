#!/usr/bin/env python3
"""
Test script to verify the backtest engine fix for strategy loading
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from bson import ObjectId

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from motor.motor_asyncio import AsyncIOMotorClient
from services.backtest.backtest_engine import BacktestEngine, TradingMode
from models.backtest import BacktestParams

async def test_strategy_loading():
    """Test that the backtest engine can properly load a strategy"""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.bot_club
    
    # Create backtest engine
    engine = BacktestEngine(db)
    
    # Create a test strategy as dictionary
    test_strategy = {
        "_id": ObjectId(),
        "user_id": ObjectId("507f1f77bcf86cd799439011"),  # Test user ID
        "name": "Test Strategy",
        "description": "A test strategy for debugging",
        "strategy_config": {
            "symbols": ["AAPL", "MSFT"],
            "timeframe": "1d",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "entry_conditions": [
                {
                    "indicator": "sma_20",
                    "comparison": "above",
                    "value": "sma_50"
                }
            ],
            "exit_conditions": [
                {
                    "indicator": "rsi",
                    "comparison": "above",
                    "value": 70
                }
            ],
            "risk_management": {
                "risk_per_trade": 0.02,
                "stop_loss": 0.05,
                "take_profit": 0.10,
                "max_position_size": 10000.0
            },
            "indicators": [
                {"name": "SMA", "params": {"period": 20}},
                {"name": "SMA", "params": {"period": 50}},
                {"name": "RSI", "params": {"period": 14}}
            ]
        },
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    # Save the strategy to the database
    result = await db.strategy.insert_one(test_strategy)
    strategy_id = str(result.inserted_id)
    
    print(f"Created test strategy with ID: {strategy_id}")
    
    try:
        # Test loading the strategy
        loaded_strategy = await engine._get_strategy_from_db(strategy_id)
        
        if loaded_strategy is None:
            print("ERROR: Failed to load strategy from database")
            return False
            
        print(f"Successfully loaded strategy: {loaded_strategy.get('name')}")
        print(f"Strategy type: {type(loaded_strategy)}")
        
        config = loaded_strategy.get('strategy_config') or loaded_strategy.get('yaml_config') or loaded_strategy.get('config')
        if config:
            print(f"Config type: {type(config)}")
            print(f"Symbols: {config.get('symbols')}")
            print(f"Entry conditions: {len(config.get('entry_conditions', []))}")
            print(f"Exit conditions: {len(config.get('exit_conditions', []))}")
            print(f"Risk management: {config.get('risk_management')}")
            print(f"Indicators: {len(config.get('indicators', []))}")
        else:
            print("No config found in strategy")
        
        # Test creating backtest parameters
        backtest_params = BacktestParams(
            strategy_id=strategy_id,
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            initial_capital=10000.0,
            timeframe="1d"
        )
        
        print("Backtest parameters created successfully")
        
        # Test the _run_backtest method (this should not fail on strategy loading)
        try:
            # This will fail on data fetching, but should not fail on strategy loading
            result = await engine._run_backtest(loaded_strategy, backtest_params)
            print("Backtest completed successfully!")
        except Exception as e:
            if "No data retrieved" in str(e) or "fetching data" in str(e).lower():
                print(f"Expected error (data fetching): {e}")
                print("Strategy loading and processing is working correctly!")
            else:
                print(f"Unexpected error: {e}")
                return False
        
        return True
        
    finally:
        # Clean up - remove the test strategy
        await db.strategy.delete_one({"_id": result.inserted_id})
        print("Cleaned up test strategy")

if __name__ == "__main__":
    asyncio.run(test_strategy_loading()) 