from enum import Enum

class TradingMode(Enum):
    """Trading execution modes"""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live" 