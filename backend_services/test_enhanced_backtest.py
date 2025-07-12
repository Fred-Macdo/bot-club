#!/usr/bin/env python3
"""
Test script to compare original backtest engine with enhanced backtest engine
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from bson import ObjectId

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.backtest.backtest_engine import BacktestEngine
from services.backtest.enhanced_backtest_engine import EnhancedBacktestEngine
from models.backtest import BacktestParams
from database.client import get_database


async def test_backtest_engines():
    """Compare original and enhanced backtest engines"""
    
    # Connect to database
    db = await get_database()
    
    # Create engine instances
    original_engine = BacktestEngine(db)
    enhanced_engine = EnhancedBacktestEngine(db)
    
    # Test parameters
    strategy_id = "507f1f77bcf86cd799439011"  # Replace with actual strategy ID
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 3, 1)
    
    backtest_params = BacktestParams(
        strategy_id=strategy_id,
        start_date=start_date,
        end_date=end_date,
        initial_capital=10000,
        timeframe="1d"
    )
    
    print("=" * 60)
    print("COMPARING BACKTEST ENGINES")
    print("=" * 60)
    
    try:
        # Test original engine
        print("\n1. Testing ORIGINAL Backtest Engine...")
        print("-" * 40)
        original_start = datetime.now()
        original_result = await original_engine.run_trading(
            strategy_id=strategy_id,
            mode=original_engine.TradingMode.BACKTEST,
            user_id="test_user",
            backtest_params=backtest_params
        )
        original_end = datetime.now()
        original_duration = (original_end - original_start).total_seconds()
        
        print(f"Original Engine Results:")
        print(f"  Total Trades: {original_result.total_trades}")
        print(f"  Total Return: {original_result.total_return:.2%}")
        print(f"  Win Rate: {original_result.win_rate:.2%}")
        print(f"  Sharpe Ratio: {original_result.sharpe_ratio:.2f}")
        print(f"  Max Drawdown: {original_result.max_drawdown:.2%}")
        print(f"  Execution Time: {original_duration:.2f} seconds")
        
    except Exception as e:
        print(f"Original engine failed: {e}")
        original_result = None
    
    try:
        # Test enhanced engine
        print("\n2. Testing ENHANCED Backtest Engine...")
        print("-" * 40)
        enhanced_start = datetime.now()
        enhanced_result = await enhanced_engine.run_trading(
            strategy_id=strategy_id,
            mode=enhanced_engine.TradingMode.BACKTEST,
            user_id="test_user",
            backtest_params=backtest_params
        )
        enhanced_end = datetime.now()
        enhanced_duration = (enhanced_end - enhanced_start).total_seconds()
        
        print(f"Enhanced Engine Results:")
        print(f"  Total Trades: {enhanced_result.total_trades}")
        print(f"  Total Return: {enhanced_result.total_return:.2%}")
        print(f"  Win Rate: {enhanced_result.win_rate:.2%}")
        print(f"  Sharpe Ratio: {enhanced_result.sharpe_ratio:.2f}")
        print(f"  Max Drawdown: {enhanced_result.max_drawdown:.2%}")
        print(f"  Execution Time: {enhanced_duration:.2f} seconds")
        
    except Exception as e:
        print(f"Enhanced engine failed: {e}")
        enhanced_result = None
    
    # Compare results
    if original_result and enhanced_result:
        print("\n3. COMPARISON SUMMARY")
        print("-" * 40)
        
        trade_diff = enhanced_result.total_trades - original_result.total_trades
        return_diff = enhanced_result.total_return - original_result.total_return
        win_rate_diff = enhanced_result.win_rate - original_result.win_rate
        
        print(f"Trade Count Difference: {trade_diff:+d} trades")
        print(f"Return Difference: {return_diff:+.2%}")
        print(f"Win Rate Difference: {win_rate_diff:+.2%}")
        
        if trade_diff > 0:
            print(f"✅ Enhanced engine generated {trade_diff} more trades!")
        else:
            print(f"❌ Enhanced engine generated {abs(trade_diff)} fewer trades")
            
        if return_diff > 0:
            print(f"✅ Enhanced engine performed {return_diff:.2%} better!")
        else:
            print(f"❌ Enhanced engine performed {abs(return_diff):.2%} worse")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_backtest_engines()) 