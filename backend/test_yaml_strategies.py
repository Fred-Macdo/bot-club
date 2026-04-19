#!/usr/bin/env python3
"""
Test script to verify YAML strategy loading works correctly
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.services.default_strategies import get_default_strategies


def test_yaml_loading():
    """Test that YAML strategies load correctly"""
    print("Testing YAML strategy loading...")

    try:
        strategies = get_default_strategies()
        print(f"✅ Successfully loaded {len(strategies)} strategies")

        for i, strategy in enumerate(strategies, 1):
            print(f"\n📊 Strategy {i}: {strategy.name}")
            print(f"   Description: {strategy.description}")
            print(f"   Symbols: {strategy.config.symbols}")
            print(f"   Timeframe: {strategy.config.timeframe}")
            print(f"   Indicators: {len(strategy.config.indicators)} configured")
            print(f"   Entry conditions: {len(strategy.config.entry_conditions)}")
            print(f"   Exit conditions: {len(strategy.config.exit_conditions)}")
            print(
                f"   Risk management: {strategy.config.risk_management.position_sizing_method}"
            )

        return True

    except Exception as e:
        print(f"❌ Error loading strategies: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_yaml_loading()
    sys.exit(0 if success else 1)
