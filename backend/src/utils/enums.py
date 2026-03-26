from enum import Enum

class TradingMode(Enum):
    """Trading execution modes"""
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"

class LogEventType(str, Enum):
    """Event types for log messages"""
    LOG = "log"
    POSITIONS = "positions"
    ACCOUNT_VALUE = "account_value"
    PRICE_DATAFRAME = "price_dataframe"
    EXIT_CONDITIONS = "exit_conditions"
    PORTFOLIO_SNAPSHOT = "portfolio_snapshot"
    INDICATOR_VALUES = "indicator_values" 

class DataProvider(str, Enum):
    """Supported data providers"""
    ALPACA = "alpaca"
    POLYGON = "polygon"
    YAHOO = "yahoo"

