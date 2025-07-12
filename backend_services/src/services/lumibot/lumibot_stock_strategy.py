from datetime import datetime
import yaml
import argparse
from typing import Dict, Union, List, Any
import os

from lumibot.strategies import Strategy
from lumibot.backtesting import YahooDataBacktesting
from lumibot.brokers import Alpaca
import polars as pl

from components.TrueBautist import TrueBautistStrategy
from ..indicators.IndicatorFactory import 


class YAMLStrategy(Strategy):
    """
    This class takes in a yaml configuration file as a strategy and runs it using Lumibot lifecycle methods. 
    """
    def initialize(self,
                   true_bautist_config: TrueBautistStrategy):
        """
        Initialize the strategy with configuration parameters.
        
        This method sets up all necessary strategy parameters including symbols,
        timeframe, indicators, entry/exit conditions, and risk management settings.
        
        Args:
            true_bautist_config (TrueBautistStrategy): Strategy configuration object
                containing all trading parameters and settings.
        """
        
        self.strategy = true_bautist_config
        self.symbols = true_bautist_config.get_config()['symbols']
        self.timeframe = true_bautist_config.get_config()['timeframe']
        self.sleeptime = "1M"  # Default sleep time, can be overridden in config
        if 'sleeptime' in true_bautist_config.get_config():
            self.sleeptime = true_bautist_config.get_config()['sleeptime']
        self.params = true_bautist_config.indicators
        self.entry_conditions = true_bautist_config.get_config()['entry_conditions']
        self.exit_conditions = true_bautist_config.get_config()['exit_conditions']
        self.risk_management = true_bautist_config.get_config()['risk_management']

    def before_market_opens(self):
        """
        Executed before market opens each day.
        
        This method initializes indicators and logs current account status
        including cash balance and portfolio value.
        """
        self.indicators = self.params
        self.log_message("\n")
        self.log_message(f"Date: {self.get_datetime()}", f"Cash Balance: {self.get_cash():.2f}", f"Account Value: {self.get_portfolio_value():.2f}") 

    def on_trading_iteration(self):
        """
        Main trading logic executed on each iteration.
        
        This method:
        1. Checks cash balance and sells all positions if cash <= 0
        2. For each symbol:
           - Gets historical price data
           - Calculates technical indicators
           - If position exists: checks exit conditions and sells if met
           - If no position: checks entry conditions and buys with risk management
        
        The method implements bracket orders with stop-loss and take-profit levels
        based on the configured risk management parameters.
        """
        cash = self.get_cash()
        positions = self.get_positions()
        self.log_message(f"Date: {self.get_datetime()}, Positions: {positions}" )
        if cash <= 0 :
            self.sell_all()
            self.sleep
            
        else:
            for symbol in self.symbols:
                
                # Get data for each symbol
                prices = self.get_historical_prices(symbol, 30)
                position = self.get_position(symbol)

                technicals = TechnicalIndicators(prices.df, self.params)
                df = technicals.calculate_indicators()
                
                if position:
                    # IF WE HAVE A POSITION, CHECK THE EXIT CONDITIONS
                    if self._check_exit_conditions(df.iloc[-1]):
                        # EVALUATES TO TRUE OR FALSE, IF TRUE SELL ALL
                        self.sell_all(symbol)
                        self.log_message(f"Selling {position.quantity} shares of {symbol}")
                
                else:
                    # CHECK IF ENTRY CONDITIONS EVALUATE TO TRUE; TAKE POSITION
                    if self._check_entry_conditions(df.iloc[-1]):
                        # Calculate the risk management
                            
                        price = df.close.iloc[-1]
                        risk_amount = cash * self.risk_management['risk_per_trade']

                        position_size = risk_amount // price 
                        stop_loss_price = price * (1 - self.risk_management['stop_loss'])
                        take_profit_price = price * (1 + self.risk_management['take_profit'])
                        stop_loss_price = stop_loss_price.round(2)
                        take_profit_price = take_profit_price.round(2)
                        # Execute the purchase
                        order = self.create_order(
                            asset=symbol,
                            quantity = position_size,
                            side="buy",
                            take_profit_price=take_profit_price,
                            stop_loss_price=stop_loss_price,
                            type="bracket"
                        )
                        self.log_message(f"Submitting Order: {symbol}, Position Size: {position_size:.0f}")
                        self.log_message(f"Total Cost (Approximate): {(position_size * df.close.iloc[-1]):.2f}")
                        
                        self.submit_order(order)   
        self.log_message("*****************************************")
    
    def _check_entry_conditions(self, row: pd.Series) -> bool:
        """
        Check if all entry conditions are met for opening a position.
        
        Args:
            row (pd.Series): Current row of indicator data
            
        Returns:
            bool: True if ALL entry conditions are satisfied, False otherwise
        """
        return all(
            self._check_condition(row, condition)
            for condition in self.entry_conditions
        )

    def _check_exit_conditions(self, row: pd.Series) -> bool:
        """
        Check if any exit condition is met for closing a position.
        
        Args:
            row (pd.Series): Current row of indicator data
            
        Returns:
            bool: True if ANY exit condition is satisfied, False otherwise
        """
        return any(
            self._check_condition(row, condition)
            for condition in self.exit_conditions
        )

    def _check_condition(self, row: pd.Series, condition_config: Dict) -> bool:
        """
        Check entry/exit condition for a given row based on indicator values and comparison logic.
        
        Args:
            row: pandas Series containing indicator values and their previous values
            condition_config: Dictionary with keys 'indicator', 'comparison', and 'value'
        
        Returns:
            bool: Whether the condition is met
        
        Raises:
            ValueError: If comparison operator is invalid
        """
        valid_comparisons = ['above', 'below', 'between', 'crosses_above', 'crosses_below', 'equals']
        comparison = condition_config['comparison']
        
        if comparison not in valid_comparisons:
            raise ValueError(f"Comparison '{comparison}' is not valid. Must be one of {valid_comparisons}")
        
        indicator = condition_config['indicator']
        value = condition_config['value']
        
        # Ensure indicator is lowercase for consistent access
        indicator_key = indicator.lower()
        
        # Handle special indicators with dedicated comparisons
        if indicator == "MACD" and comparison in ["crosses_above", "crosses_below"]:
            return self._check_macd_cross(row, comparison)
        
        elif indicator == "BBANDS" and comparison in ["crosses_above", "crosses_below"]:
            return self._check_bbands_cross(row, comparison, value)
        
        # Handle general comparison cases
        if comparison == "above":
            return self._check_above(row, indicator_key, value)
        
        elif comparison == "below":
            return self._check_below(row, indicator_key, value)
        
        elif comparison == "crosses_above":
            return self._check_crosses_above(row, indicator_key, value)
        
        elif comparison == "crosses_below":
            return self._check_crosses_below(row, indicator_key, value)
        
        elif comparison == "between":
            # The original code had a bug here - it used 'indicator == between'
            # The correct check should be looking at the indicator value being between bounds
            return self._check_between(row, indicator_key, value)
        
        elif comparison == "equals":
            """Check if indicator equals a value or another indicator"""
            if isinstance(value, str):
                return row[indicator_key] == row[value.lower()]
            else:  # int, float
                return row[indicator_key] == value

            
        # Default fallback (should never reach here due to validation)
        return False

    def _check_above(self, row: pd.Series, indicator_key: str, value: Union[str, int, float]) -> bool:
        """
        Check if indicator is above a value or another indicator.
        
        Args:
            row (pd.Series): Current row of indicator data
            indicator_key (str): The indicator to check (lowercase)
            value (Union[str, int, float]): Value to compare against - can be numeric
                or another indicator name
                
        Returns:
            bool: True if indicator > value, False otherwise
        """
        if isinstance(value, str):
            return row[indicator_key] > row[value.lower()]
        else:  # int, float
            return row[indicator_key] > value

    def _check_below(self, row: pd.Series, indicator_key: str, value: Union[str, int, float]) -> bool:
        """
        Check if indicator is below a value or another indicator.
        
        Args:
            row (pd.Series): Current row of indicator data
            indicator_key (str): The indicator to check (lowercase)
            value (Union[str, int, float]): Value to compare against - can be numeric
                or another indicator name
                
        Returns:
            bool: True if indicator < value, False otherwise
        """
        if isinstance(value, str):
            return row[indicator_key] < row[value.lower()]
        else:  # int, float
            return row[indicator_key] < value

    def _check_crosses_above(self, row: pd.Series, indicator_key: str, value: Union[str, int, float]) -> bool:
        """
        Check if indicator crosses above a value or another indicator.
        
        A crossover occurs when the indicator was below/equal to the value in the
        previous period and is now above it in the current period.
        
        Args:
            row (pd.Series): Current row of indicator data (must include _prev columns)
            indicator_key (str): The indicator to check (lowercase)
            value (Union[str, int, float]): Value to compare against - can be numeric
                or another indicator name
                
        Returns:
            bool: True if indicator crosses above value, False otherwise
        """
        if isinstance(value, str):
            value_key = value.lower()
            evaluation = (row[indicator_key] > row[value_key]) and (row[f"{indicator_key}_prev"] <= row[f"{value_key}_prev"])
            if evaluation:
                self.log_message("Crosses above evaluation")
                self.log_message(f"Current Values: {indicator_key}: {row[indicator_key]:.2f}, {value_key}: {row[value_key]:.2f}")
                self.log_message(f"Previous values: {indicator_key}_prev: {row[f'{indicator_key}_prev']:.2f}, {value_key}_prev: {row[f'{value_key}_prev']:.2f}")
            return evaluation
        else:  # int, float
            evaluation = (row[indicator_key] > value) and (row[f"{indicator_key}_prev"] <= value)
            if evaluation:
                self.log_message("Crosses above evaluation, numerical value")
                self.log_message(f"Current Values: {indicator_key}: {row[indicator_key]:.2f}")
                self.log_message(f"Previous Values: {indicator_key}_prev: {row[f'{indicator_key}_prev']:.2f}, value: {value:.2f}")
            return evaluation


    def _check_crosses_below(self, row: pd.Series, indicator_key: str, value: Union[str, int, float]) -> bool:
        """
        Check if indicator crosses below a value or another indicator.
        
        A crossunder occurs when the indicator was above/equal to the value in the
        previous period and is now below it in the current period.
        
        Args:
            row (pd.Series): Current row of indicator data (must include _prev columns)
            indicator_key (str): The indicator to check (lowercase)
            value (Union[str, int, float]): Value to compare against - can be numeric
                or another indicator name
                
        Returns:
            bool: True if indicator crosses below value, False otherwise
        """
        if isinstance(value, str):
            value_key = value.lower()
            evaluation = (row[indicator_key] < row[value_key]) and (row[f"{indicator_key}_prev"] >= row[f"{value_key}_prev"])
            if evaluation:
                self.log_message("Crosses below evaluation")
                self.log_message(f"Current Values: {indicator_key}: {row[indicator_key]:.2f}, {value_key}: {row[value_key]:.2f}")
                self.log_message(f"Previous values: {indicator_key}_prev: {row[f'{indicator_key}_prev']:.2f}, {value_key}_prev: {row[f'{value_key}_prev']:.2f}")
            return evaluation
        else:  # int, float
            evaluation = (row[indicator_key] < value) and (row[f"{indicator_key}_prev"] >= value)
            if evaluation:
                self.log_message("Crosses below evaluation, numerical value")
                self.log_message(f"Current Values: {indicator_key}: {row[indicator_key]:.2f}")
                self.log_message(f"Previous Values: {indicator_key}_prev: {row[f'{indicator_key}_prev']:.2f}, value: {value:.2f}")
            return evaluation


    def _check_between(self, row: pd.Series, indicator_key: str, value: List[Union[str, int, float]]) -> bool:
        """
        Check if indicator value is between two bounds (inclusive).
        
        Args:
            row (pd.Series): Current row of indicator data
            indicator_key (str): The indicator to check (lowercase)
            value (List[Union[str, int, float]]): List with exactly 2 elements
                representing [lower_bound, upper_bound]. Can be numeric values
                or other indicator names.
                
        Returns:
            bool: True if lower_bound <= indicator <= upper_bound, False otherwise
            
        Note:
            Handles both pandas versions with and without scalar .between() method.
        """
        try:
            # Try using scalar between method if it's available on this pandas version
            if all(isinstance(x, (int, float)) for x in value):
                return row[indicator_key].between(value[0], value[1])
            else:
                lower_value = row[value[0].lower()] if isinstance(value[0], str) else value[0]
                upper_value = row[value[1].lower()] if isinstance(value[1], str) else value[1]
                return row[indicator_key].between(lower_value, upper_value)
        except AttributeError:
            # Fallback for older pandas versions or if the value doesn't support between
            if all(isinstance(x, (int, float)) for x in value):
                return (value[0] <= row[indicator_key]) and (row[indicator_key] <= value[1])
            else:
                lower_value = row[value[0].lower()] if isinstance(value[0], str) else value[0]
                upper_value = row[value[1].lower()] if isinstance(value[1], str) else value[1]
                return (lower_value <= row[indicator_key]) and (row[indicator_key] <= upper_value)


    def _check_macd_cross(self, row: pd.Series, comparison: str) -> bool:
        """
        Handle MACD specific crossing logic between MACD line and signal line.
        
        Args:
            row (pd.Series): Current row of indicator data containing MACD values
            comparison (str): Either 'crosses_above' or 'crosses_below'
            
        Returns:
            bool: True if MACD crosses signal line in specified direction, False otherwise
            
        Note:
            - crosses_above: MACD line crosses above signal line (bullish signal)
            - crosses_below: MACD line crosses below signal line (bearish signal)
        """
        if comparison == "crosses_above":
            evaluation = (row['macd'] > row['macd_signal']) and (row['macd_prev'] <= row['macdsignal_prev'])
            if evaluation:
                self.log_message("MACD crosses above signal")
                self.log_message(f"MACD: {row['macd']:.2f}, Signal: {row['macd_signal']:.2f}")
                self.log_message(f"MACD_prev: {row['macd_prev']:.2f}, Signal_prev: {row['macdsignal_prev']:.2f}")
            return evaluation
        else:  # crosses_below
            evaluation = (row['macd'] < row['macd_signal']) and (row['macd_prev'] >= row['macdsignal_prev'])
            if evaluation:
                self.log_message("MACD crosses below signal")
                self.log_message(f"MACD: {row['macd']:.2f}, Signal: {row['macd_signal']:.2f}")
                self.log_message(f"MACD_prev: {row['macd_prev']:.2f}, Signal_prev: {row['macdsignal_prev']:.2f}")
            return evaluation


    def _check_bbands_cross(self, row: pd.Series, comparison: str, value: str) -> bool:
        """
        Handle Bollinger Bands specific crossing logic between price and bands.
        
        Args:
            row (pd.Series): Current row of indicator data containing price and band values
            comparison (str): Either 'crosses_above' or 'crosses_below'
            value (str): The Bollinger Band to check against (e.g., 'upper_band', 'lower_band')
            
        Returns:
            bool: True if price crosses the specified band in the given direction, False otherwise
            
        Note:
            - crosses_above: Price crosses above the specified band (potential overbought)
            - crosses_below: Price crosses below the specified band (potential oversold)
        """
        value_key = value.lower() if isinstance(value, str) else value
        
        if comparison == "crosses_above":
            evaluation = (row['close'] > row[value_key]) and (row['close_prev'] <= row[value_key])
            if evaluation:
                self.log_message("Price crosses above Bollinger Band")
                self.log_message(f"Close: {row['close']:.2f}, {value_key}: {row[value_key]:.2f}")
                self.log_message(f"Close_prev: {row['close_prev']:.2f}, {value_key}_prev: {row[value_key]:.2f}")
            return evaluation
        else:  # crosses_below
            evaluation = (row['close'] < row[value_key]) and (row['close_prev'] >= row[value_key])
            if evaluation:
                self.log_message("Price crosses below Bollinger Band")
                self.log_message(f"Close: {row['close']:.2f}, {value_key}: {row[value_key]:.2f}")
                self.log_message(f"Close_prev: {row['close_prev']:.2f}, {value_key}_prev: {row[value_key]:.2f}")
            return evaluation
  
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automated Trading Strategy Backtester')
    parser.add_argument('-c','--config', 
                        required=True,
                        help='Trading strategy YAML Config to backtest')
    parser.add_argument('-k','--api_keys',
                        required=True,
                        help='API Keys for Live Trading')
    parser.add_argument("mode", choices=["live", "paper", "backtest"],
                        help="Run mode: 'live' for live trading on real money account, 'paper' for live trading on paper account, 'backtest' for historical testing")
    
    
    args = parser.parse_args()


    if args.api_keys:
        api_keys = args.api_keys 

    with open(api_keys, 'r') as file:
        keys = yaml.safe_load(file)

    with open(args.config, 'r') as file:
        yaml_trade_config = yaml.safe_load(file)

    strategy = TrueBautistStrategy(yaml_trade_config, keys)
    print(strategy.get_config())
    
    ALPACA_CONFIG = {
    # Put your own Alpaca key here:
    "API_KEY": keys["API_KEY"],
    # Put your own Alpaca secret here:
    "API_SECRET": keys["API_SECRET"],
    # If you want to go live, you must change this
    "PAPER": True,
    }
    
    
    
    if args.mode == 'live':
        # LIVE TRADE; ENSURE LIVE API KEYS IN COMMAND LINE ARGS
        ALPACA_CONFIG = ALPACA_CONFIG['PAPER'] = False
        broker = Alpaca(ALPACA_CONFIG)

        lumistrategy = YAMLStrategy(broker=broker, true_bautist_config=strategy, save_logfile=True)
        lumistrategy.run_live()

    elif args.mode == 'paper':
        # PAPER TRADE; ENSURE PAPER API KEYS IN COMMAND LINE ARGS
        broker = Alpaca(ALPACA_CONFIG)

        lumistrategy = YAMLStrategy(broker=broker, true_bautist_config=strategy, save_logfile=True)
        lumistrategy.run_live()
    else:
        # BACKTEST ONLY
        backtesting_start = datetime.strptime(strategy.config['start_date'], "%Y-%m-%d")
        backtesting_end = datetime.strptime(strategy.config['end_date'], "%Y-%m-%d")
        YAMLStrategy.backtest(YahooDataBacktesting,
                            backtesting_start=backtesting_start,
                            backtesting_end=backtesting_end, 
                            parameters={'true_bautist_config': strategy}, 
                            logfile=os.path.join('logs', f"log_{datetime.now().strftime('%d%m%Y_%H-%M-%S')}.log"))