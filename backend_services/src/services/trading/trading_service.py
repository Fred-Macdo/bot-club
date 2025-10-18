from lumibot.strategies import Strategy
from lumibot.entities import Asset, Position
from lumibot.backtesting import YahooDataBacktesting
from lumibot.brokers import Alpaca

from datetime import datetime
import pandas as pd
from typing import Dict, Union, List, Any
import numpy as np
import logging
from ..indicators.indicator_factory import IndicatorFactory
from ..utils.condition_checker import ConditionChecker
from ..utils.indicator_converter import IndicatorConverter
from ..utils.trade_logger import TradeLogger
from ..utils.websocket_manager import WebSocketLogHandler
from alpaca.trading.client import TradingClient

# paper=True enables paper trading
logger = logging.getLogger(__name__)

# Set consistent formatting options at the beginning of the script
pd.set_option('display.precision', 2)
np.set_printoptions(precision=2, suppress=True)  # Added suppress=True to avoid scientific notation

class CryptoStrategy(Strategy):
    """
    This class takes in a yaml configuration file as a strategy and runs it using Lumibot lifecycle methods. 

    Args:
        strategy_config: Dict[str, Any] - The strategy configuration
            - symbols: List[str] - The symbols to trade
            - timeframe: str - The timeframe to trade
            - indicators: List[Dict[str, Any]] - The indicators to use
            - entry_conditions: List[Dict[str, Any]] - The entry conditions to use
            - exit_conditions: List[Dict[str, Any]] - The exit conditions to use
            - risk_management: Dict[str, Any] - The risk management to use
            - dca_enabled: bool - Whether to use DCA
            - max_dca_positions: int - The maximum number of DCA positions
    """
    def initialize(self,
                   strategy_config: Dict[str, Any]):
        
       
        self.strategy = strategy_config
        self.symbols = strategy_config.get('symbols', [])
        self.timeframe = strategy_config.get('timeframe', '15Min')
        self.sleeptime = '5S'
        self.params = strategy_config.get('indicators', [])
        self.entry_conditions = strategy_config.get('entry_conditions', [])
        self.exit_conditions = strategy_config.get('exit_conditions', [])
        self.risk_management = strategy_config.get('risk_management', {})
        self.set_market("24/7")
        

    def on_trading_iteration(self):
        # Get the cash balance, positions, and portfolio value
        cash = self.get_cash()
        positions = self.get_positions()
        self.log_message(f"Date: {self.get_datetime()}", f"Cash Balance: {self.get_cash():.2f}", f"Account Value: {self.get_portfolio_value():.2f}")
        self.log_message(f"Current Positions: {positions}")
        # If the cash balance is less than 0, sell all positions and sleep
        if cash <= 0 :
            self.sleep
            
        else:
            # 1. Get the assets
            # 2. Get the last price for each asset
            # 3. Get the data for each asset
            # 4. Calculate the indicators for each asset
            # 5. Check the exit conditions for each asset
            # 6. If we have a position, check if the exit conditions are met, if so; sell all positions for that asset
            # 7. if we have a position, check if the stop loss is hit, if so; sell all positions for that asset
            # 8. if we have a position, check if the take profit is hit, if so; sell all positions for that asset
            # 9. if we have a position, check if the DCA entry conditions are met, if so; buy the asset
            # 10. If we don't have a position, check if the entry conditions are met, if so; buy the asset

            # 1. Get the assets
            assets = [Asset(x, asset_type=Asset.AssetType.CRYPTO) for x in self.symbols]
            for asset in assets: 
                # 2. Get the last price for each asset
                base = asset
                quote = Asset(symbol="USD", asset_type=Asset.AssetType.FOREX)
                
                #  3. Get data for each symbol
                prices = self.get_historical_prices(base, 2, "day", quote=quote)
                self.log_message(f"LatestPrices: {prices}")
                position = self.get_position(asset)

                # 4. Calculate the indicators for each asset
                technicals = IndicatorFactory(prices.df, self.params)
                self.log_message(f"Calculating indicators with params: {self.params}")
                df = technicals.calculate_indicators()
                latest_data = df.row(-1, named=True)
                self.log_message(f"Latest price data:\n {latest_data}")            
                self.log_message(f"Position: {position}, type: {type(position)}")
                if len(position) > 0:
                    # 5. IF WE HAVE A POSITION, CHECK THE EXIT CONDITIONS
                    if self._check_exit_conditions(latest_data, asset):
                        # 6. EVALUATES TO TRUE OR FALSE, IF TRUE SELL ALL
                        order = self.create_order(
                            asset=base,
                            quantity=position.quantity,
                            side="sell"
                        )
                        self.submit_order(order)
                    
                    # 9. if we have a position, check if the DCA entry conditions are met, 
                    #    if so; buy the asset

                        self.submit_order(order)
                        self.log_message(f"DCA Entry: \n Buying {position_size} shares of {asset} at price {df.close.iloc[-1]:.2f}")
                    # 10. If we don't have a position, check if the entry conditions are met, if so; buy the asset
                else:
                    if self._check_entry_conditions(df.iloc[-1]):
                        position_size = self._calculate_position_size(asset, df.close.iloc[-1])
                        quote = Asset("USD", asset_type="forex")

                        order = self.create_order(
                            asset=base,
                            quantity=position_size,
                            side="buy"
                        )
                        self.submit_order(order)
                        self.log_message(f"Entry: \n Buying {position_size} shares of {asset} at price {df.close.iloc[-1]:.2f}")
        self.log_message("**********************************************************************************")
    def on_abrupt_closing(self):
        # Sell all positions
        self.sell_all()

    ######################################
    ########## HELPER FUNCTIONS ##########
    ######################################

    def _check_entry_conditions(self, row: pd.Series) -> bool:
        """Check if all entry conditions are met"""
        return ConditionChecker.check_entry_conditions(self.entry_conditions, row)

    def _check_exit_conditions(self, row: pd.Series, asset: Asset) -> bool:
        """Check if any exit condition is met"""
        return ConditionChecker.check_exit_conditions(self.exit_conditions, row, self.get_position(asset), self.get_datetime())

    def _get_position(self, asset: Asset) -> Position:
        return self.get_position(asset)

    def _get_datetime(self) -> datetime:
        return self.get_datetime()

    def _get_cash(self) -> float:
        return self.get_cash()

    def _get_portfolio_value(self) -> float:
        return self.get_portfolio_value()   
  
