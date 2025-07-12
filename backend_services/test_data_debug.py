#!/usr/bin/env python3
"""
Debug script to check data structure and columns
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from motor.motor_asyncio import AsyncIOMotorClient
from services.backtest.backtest_engine import BacktestEngine

async def debug_data_structure():
    """Debug the data structure to see what columns are available"""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.bot_club
    
    # Create backtest engine
    engine = BacktestEngine(db)
    
    # Test data fetching
    symbols = ["AAPL"]
    start_date = "2023-01-01"
    end_date = "2023-01-10"  # Just a few days for testing
    timeframe = "1d"
    
    print(f"Fetching data for {symbols} from {start_date} to {end_date}")
    
    try:
        # Fetch data
        data = await engine._fetch_historical_data(symbols, start_date, end_date, timeframe)
        
        print(f"Data shape: {data.shape}")
        print(f"Data columns: {data.columns}")
        print(f"Data types: {data.dtypes}")
        
        # Show first few rows
        print("\nFirst 3 rows:")
        print(data.head(3))
        
        # Test indicator calculation
        from services.indicators.IndicatorFactory import IndicatorFactory
        
        symbol_df = data.filter(data["symbol"] == "AAPL")
        print(f"\nSymbol data shape: {symbol_df.shape}")
        print(f"Symbol data columns: {symbol_df.columns}")
        
        # Test indicator factory
        indicator_params = {'sma': {'period': 20}, 'ema': {'period': 5}, 'rsi': {'period': 14}}
        indicator_factory = IndicatorFactory(symbol_df, indicator_params)
        indicators = indicator_factory.get_indicators()
        
        if indicators is not None and len(indicators) > 0:
            print(f"\nIndicator data shape: {indicators.shape}")
            print(f"Indicator columns: {indicators.columns}")
            print("\nFirst 3 rows of indicators:")
            print(indicators.head(3))
        else:
            print("No indicators generated")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_data_structure()) 