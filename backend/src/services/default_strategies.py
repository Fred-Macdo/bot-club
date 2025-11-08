    # backend/services/default_strategies.py
import asyncio
import logging
from datetime import datetime
import hashlib
import json

from pymongo.database import Database
from typing import Dict, Any, List

from ..models.strategy import Strategy
from ..utils.db_executor import run_db_operation

# Default strategies configuration
DEFAULT_STRATEGIES = [
    {
        "key": "ema_crossover_v1",  # Unique identifier for this default strategy
        "name": "EMA Crossover Strategy",
        "description": "Basic EMA crossover with RSI filter - a trend-following strategy",
        "config": {
            "symbols": ["AAPL", "MSFT", "GOOG"],
            "timeframe": "1d",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "entry_conditions": [
                {
                    "indicator": "ema_5",
                    "comparison": "crosses_above",
                    "value": "ema_20"
                }
            ],
            "exit_conditions": [
                {
                    "indicator": "ema_5",
                    "comparison": "crosses_below",
                    "value": "ema_20"
                }
            ],
            "risk_management": {
                "position_sizing_method": "risk_based",
                "risk_per_trade": 0.02,
                "stop_loss": 0.05,
                "take_profit": 0.15,
                "max_position_size": 10000,
                "atr_multiplier": 2
            },
            "indicators": [
                {"name": "EMA", "params": {"period": 5}},
                {"name": "EMA", "params": {"period": 20}},
                {"name": "RSI", "params": {"period": 14}}
            ]
        }
    },
    {
        "key": "bollinger_bands_v1",
        "name": "Bollinger Bands Strategy",
        "description": "Mean reversion strategy using Bollinger Bands",
        "config": {
            "symbols": ["SPY", "QQQ"],
            "timeframe": "1h",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "entry_conditions": [
                {
                    "indicator": "close",
                    "comparison": "below",
                    "value": "lowerband"
                }
            ],
            "exit_conditions": [
                {
                    "indicator": "close",
                    "comparison": "above",
                    "value": "middleband"
                }
            ],
            "risk_management": {
                "position_sizing_method": "risk_based",
                "risk_per_trade": 0.015,
                "stop_loss": 0.03,
                "take_profit": 0.06,
                "max_position_size": 15000,
                "atr_multiplier": 1.5
            },
            "indicators": [
                {"name": "BBANDS", "params": {"period": 20, "std_dev": 2}},
                {"name": "RSI", "params": {"period": 14}}
            ]
        }
    },
    {
        "key": "rsi_reversal_v1",
        "name": "RSI Reversal Strategy",
        "description": "Momentum reversal strategy based on RSI oversold/overbought conditions",
        "config": {
            "symbols": ["TSLA", "NVDA", "AMD"],
            "timeframe": "4h",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "entry_conditions": [
                {
                    "indicator": "rsi",
                    "comparison": "below",
                    "value": "30"
                }
            ],
            "exit_conditions": [
                {
                    "indicator": "rsi",
                    "comparison": "above",
                    "value": "70"
                }
            ],
            "risk_management": {
                "position_sizing_method": "risk_based",
                "risk_per_trade": 0.025,
                "stop_loss": 0.04,
                "take_profit": 0.12,
                "max_position_size": 20000,
                "atr_multiplier": 2.5
            },
            "indicators": [
                {"name": "RSI", "params": {"period": 14}},
                {"name": "SMA", "params": {"period": 50}}
            ]
        }
    }
]

async def initialize_default_strategies(db: Database) -> None:
    """
    Initialize default strategies in the database.
    This function ensures that default strategies are created only once.
    """
    default_strategies_collection = db["default_strategies"]
    
    for strategy in DEFAULT_STRATEGIES:
        # Check if this default strategy already exists using its unique key
        existing = await default_strategies_collection.find_one({"key": strategy["key"]})
        
        if not existing:
            # Strategy doesn't exist, so create it
            await default_strategies_collection.insert_one({
                **strategy,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "version": "1.0"  # Version tracking for future updates
            })
            print(f"Created default strategy: {strategy['name']}")
        else:
            # Strategy exists, check if it needs updating (optional)
            # You could implement version checking here if needed
            print(f"Default strategy already exists: {strategy['name']}")

async def get_default_strategies_from_db(db: Database) -> List[Dict[str, Any]]:
    """
    Retrieve all default strategies from the database.
    These are templates that users can view but not modify.
    """
    default_strategies_collection = db["default_strategies"]
    strategies = []
    
    async for strategy in default_strategies_collection.find({}):
        # Remove MongoDB-specific fields that shouldn't be exposed
        #strategy.pop("_id", None)
        strategy.pop("key", None)  # Hide internal key from frontend
        strategies.append(strategy)
    
    return strategies

async def create_checksum_for_strategy(strategy_config: Dict[str, Any]) -> str:
    """
    Create a checksum for a strategy configuration to detect changes.
    This helps in determining if a default strategy has been updated.
    """
    # Sort the dictionary to ensure consistent hashing
    config_string = json.dumps(strategy_config, sort_keys=True)
    return hashlib.sha256(config_string.encode()).hexdigest()

async def update_default_strategies_if_needed(db: Database) -> None:
    """
    Check if any default strategies need updating based on version or checksum.
    This is useful when you update your default strategies in code.
    """
    default_strategies_collection = db["default_strategies"]
    
    for strategy in DEFAULT_STRATEGIES:
        existing = await default_strategies_collection.find_one({"key": strategy["key"]})
        
        if existing:
            # Create checksums to compare
            existing_checksum = await create_checksum_for_strategy(existing.get("config", {}))
            new_checksum = await create_checksum_for_strategy(strategy["config"])
            
            if existing_checksum != new_checksum:
                # Strategy has changed, update it
                await default_strategies_collection.update_one(
                    {"key": strategy["key"]},
                    {
                        "$set": {
                            **strategy,
                            "updated_at": datetime.utcnow(),
                            "previous_version": existing.get("version", "1.0"),
                            "version": "1.1"  # Increment version
                        }
                    }
                )
                print(f"Updated default strategy: {strategy['name']}")

async def get_default_strategies(db: Database) -> List[Dict[str, Any]]:
    """Fetches default strategies from the database."""
    cursor = db.strategy.find({"is_default": True})
    strategies = await run_db_operation(list, cursor)
    return strategies

async def insert_default_strategies(db: Database, strategies: List[Dict[str, Any]]):
    """Inserts default strategies if they don't already exist."""
    await run_db_operation(
        db.strategy.insert_many,
        strategies,
        ordered=False  # Continue on duplicate key errors
    )