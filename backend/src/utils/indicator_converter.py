import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class IndicatorConverter:
    """Wrapper class around indicator conversion utilities."""

    @staticmethod
    def convert_indicators_to_params(indicators: List[Dict]) -> Dict:
        return convert_indicators_to_params(indicators)

    @staticmethod
    def validate_indicator_params(indicator: Dict) -> bool:
        return validate_indicator_params(indicator)


def convert_indicators_to_params(indicators: List[Dict]) -> Dict:
    """Convert strategy indicators to IndicatorFactory parameters"""
    params = {}

    for indicator in indicators:
        name = indicator.get("name", "").lower()
        indicator_params = indicator.get("params", {})

        # Handle indicators that need period-based naming
        if name in ["sma", "ema"]:
            period = indicator_params.get("period", 20)
            key = f"{name}_{period}"
            params[key] = indicator_params
        elif name == "rsi":
            params["rsi"] = indicator_params
        elif name in ("bollinger_bands", "bbands"):
            params["bbands"] = {
                "period": indicator_params.get("period", 20),
                "std": indicator_params.get("std", indicator_params.get("std_dev", 2)),
            }
        elif name == "macd":
            params["macd"] = {
                "fast_period": indicator_params.get(
                    "fast_period", indicator_params.get("fast", 12)
                ),
                "slow_period": indicator_params.get(
                    "slow_period", indicator_params.get("slow", 26)
                ),
                "signal_period": indicator_params.get(
                    "signal_period", indicator_params.get("signal", 9)
                ),
            }
        elif name == "atr":
            params["atr"] = indicator_params
        elif name == "adx":
            params["adx"] = indicator_params
        elif name == "obv":
            params["obv"] = {}
        elif name == "mfi":
            params["mfi"] = indicator_params
        elif name == "cci":
            params["cci"] = indicator_params
        elif name == "vwap":
            params["vwap"] = indicator_params
        else:
            # For any other indicators, use the name as is
            params[name] = indicator_params

    return params


def validate_indicator_params(indicator: Dict) -> bool:
    """Validate indicator parameters"""
    name = indicator.get("name", "").lower()
    params = indicator.get("params", {})

    # Basic validation for common indicators
    if name in ["sma", "ema"]:
        period = params.get("period")
        if not period or not isinstance(period, (int, float)) or period <= 0:
            logger.warning(f"Invalid period for {name}: {period}")
            return False

    elif name == "rsi":
        period = params.get("period")
        if not period or not isinstance(period, (int, float)) or period <= 0:
            logger.warning(f"Invalid period for RSI: {period}")
            return False

    elif name in ("bollinger_bands", "bbands"):
        period = params.get("period")
        std_dev = params.get("std", params.get("std_dev"))
        if not period or not isinstance(period, (int, float)) or period <= 0:
            logger.warning(f"Invalid period for Bollinger Bands: {period}")
            return False
        if not std_dev or not isinstance(std_dev, (int, float)) or std_dev <= 0:
            logger.warning(f"Invalid std_dev for Bollinger Bands: {std_dev}")
            return False

    return True
