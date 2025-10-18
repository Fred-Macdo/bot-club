import polars as pl
import polars_talib as plta

class IndicatorFactory:
    def __init__(self, df, params=None):
        """
        Initialize with polars DataFrame and optional parameter dictionary
        for technical indicators.
        Args:
            df: DataFrame with OHLCV data
            params: Dictionary of parameters for each indicator
        """
        self.df = df.clone()
        # Parse and organize parameters to handle multiple indicators of same type
        self.params = self._parse_indicator_params(params) if params else self._get_default_params()

    def _parse_indicator_params(self, params):
        """
        Parse indicator parameters to handle multiple indicators of the same type
        with different parameters (e.g., ema_5, ema_10, sma_20, sma_50)
        
        Args:
            params: Dictionary of indicator parameters
            
        Returns:
            Dictionary with properly keyed indicators
        """
        parsed_params = {}
        
        for indicator_name, indicator_params in params.items():
            # Handle indicators that need period-based naming (EMA, SMA)
            if indicator_name.lower() in ['ema', 'sma']:
                period = indicator_params.get('period', 20)
                key = f"{indicator_name.lower()}_{period}"
                parsed_params[key] = indicator_params
            else:
                # For other indicators, use the name as is
                parsed_params[indicator_name.lower()] = indicator_params
        
        return parsed_params

    def _get_default_params(self):
        """Get default parameters for indicators"""
        return {
            'sma_20': {'period': 20},
            'ema_20': {'period': 20},
            'rsi': {'period': 14},
            'macd': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
            'bollinger_bands': {'period': 20, 'std': 2},
            'atr': {'period': 14},
            'adx': {'period': 14},
            'obv': {},  # No parameters needed
            'mfi': {'period': 14},
            'cci': {'period': 20},
            'vwap': {'period': 5}
        }

    def calculate_sma(self, period):
        """
        Calculate Simple Moving Average (SMA)
        
        Args:
            period: Period for SMA
        """
        return pl.col("close").ta.sma(period).over("symbol").alias(f'sma_{period}')
    
    def calculate_ema(self, period):
        """
        Calculate Exponential Moving Average (EMA)
        
        Args:
            period: Period for EMA
        """
        return pl.col("close").ta.ema(period).over("symbol").alias(f'ema_{period}')

    def calculate_rsi(self, period):
        """
        Calculate Relative Strength Index (RSI)
        
        Args:
            period: Period for RSI
        """
        return pl.col("close").ta.rsi(period).over("symbol").alias(f'rsi')
    
    def calculate_macd(self, fast_period=12, slow_period=26, signal_period=9):
        """
        Calculate Moving Average Convergence Divergence (MACD)
        
        Args:
            fast_period: Fast period for MACD
            slow_period: Slow period for MACD
            signal_period: Signal period for MACD
        """
        return [
            pl.col("close").ta.macd(fast_period, slow_period, signal_period).over("symbol").struct.field("macd").alias("macd_line"),
            pl.col("close").ta.macd(fast_period, slow_period, signal_period).over("symbol").struct.field("macdsignal").alias("macd_signal"),
            pl.col("close").ta.macd(fast_period, slow_period, signal_period).over("symbol").struct.field("macdhist").alias("macd_hist")
        ]
    
    def calculate_bollinger_bands(self, period, std):
        """
        Calculate Bollinger Bands
        
        Args:
            period: Period for Bollinger Bands
            std: Standard deviation multiplier
        """
        # Bollinger Bands returns a struct with upper, middle, and lower bands
        return [
            pl.col("close").ta.bbands(period, std).struct.field("upperband").over("symbol").alias(f'upperband'),
            pl.col("close").ta.bbands(period, std).struct.field("middleband").over("symbol").alias(f'middleband'),
            pl.col("close").ta.bbands(period, std).struct.field("lowerband").over("symbol").alias(f'lowerband')
        ]
    
    def calculate_atr(self, period):
        """
        Calculate Average True Range (ATR)
        
        Args:
            period: Period for ATR
        """
        return plta.atr(
            pl.col("high"),
            pl.col("low"),
            pl.col("close"),
            timeperiod=period
        ).over("symbol").alias(f'atr')
    
    def calculate_adx(self, period):
        """
        Calculate Average Directional Index (ADX)
        
        Args:
            period: Period for ADX
        """
        return plta.adx(
            pl.col("high"),
            pl.col("low"),
            pl.col("close"),
            timeperiod=period
        ).over("symbol").alias(f'adx')
    
    def calculate_obv(self):
        """
        Calculate On Balance Volume (OBV)
        """
        return plta.obv(
            pl.col("close"),
            pl.col("volume")
        ).over("symbol").alias(f'obv')
    
    def calculate_mfi(self, period):
        """
        Calculate Money Flow Index (MFI)
        
        Args:
            period: Period for MFI
        """
        return plta.mfi(
            pl.col("high"),
            pl.col("low"),
            pl.col("close"),
            pl.col("volume"),
            timeperiod=period
        ).over("symbol").alias(f'mfi')
    
    def calculate_cci(self, period):
        """
        Calculate Commodity Channel Index (CCI)
        
        Args:
            period: Period for CCI
        """
        return plta.cci(
            pl.col("high"),
            pl.col("low"),
            pl.col("close"),
            timeperiod=period
        ).over("symbol").alias(f'cci')
    
    def calculate_vwap(self, period):
        """
        Calculate Volume Weighted Average Price (VWAP)
        
        Args:
            period: Period for VWAP (for rolling window)
        """
        # VWAP is typically calculated as (price * volume) / volume over a period
        # Using a rolling window approach
        return (
            (pl.col("close") * pl.col("volume"))
            .rolling_sum(window_size=period, min_periods=1)
            .over("symbol") / 
            pl.col("volume").rolling_sum(window_size=period, min_periods=1).over("symbol")
        ).alias(f'vwap_calc')

    def calculate_indicators(self):
        """
        Calculate all technical indicators using parameters from self.params
        """
        # Dictionary mapping indicator names to their calculation methods
        indicator_methods = {
            'sma': lambda params: self.calculate_sma(params['period']),
            'ema': lambda params: self.calculate_ema(params['period']),
            'rsi': lambda params: self.calculate_rsi(params['period']),
            'macd': lambda params: self.calculate_macd(params.get('fast_period', 12), params.get('slow_period', 26), params.get('signal_period', 9)),
            'bbands': lambda params: self.calculate_bollinger_bands(params['period'], params['std']),
            'atr': lambda params: self.calculate_atr(params['period']),
            'adx': lambda params: self.calculate_adx(params['period']),
            'obv': lambda params: self.calculate_obv(),
            'mfi': lambda params: self.calculate_mfi(params['period']),
            'cci': lambda params: self.calculate_cci(params['period']),
            'vwap': lambda params: self.calculate_vwap(params['period'])
        }
        
        # Collect all expressions to apply
        expressions = []
        
        # Process each indicator
        for indicator_key, indicator_params in self.params.items():
            # Extract the base indicator name (e.g., 'ema' from 'ema_5')
            base_name = indicator_key.split('_')[0] if '_' in indicator_key else indicator_key
            
            if base_name in indicator_methods:
                result = indicator_methods[base_name](indicator_params)
                # Handle both single expressions and lists of expressions
                if isinstance(result, list):
                    expressions.extend(result)
                else:
                    expressions.append(result)
        
        # Apply all expressions at once for efficiency
        if expressions:
            self.df = self.df.with_columns(expressions)
        
        return self.df

    def _calculate_previous_values(self) -> pl.DataFrame:
        '''
        Get all the previous values for close + indicator columns
        '''
        result_df = self.df.clone()
        exclude_cols = ['open', 'high', 'low', 'volume', 'trade_count', 'vwap'] # don't get prev values
        prev_col_list = [col for col in result_df.columns if col not in exclude_cols]
        
        # Create expressions for all previous value columns
        prev_expressions = []
        for col in prev_col_list:
            if col in result_df.columns:
                prev_expressions.append(
                    pl.col(col).shift(1).over("symbol").alias(f'{col}_prev')
                )
        
        # Apply all shift operations at once
        if prev_expressions:
            result_df = result_df.with_columns(prev_expressions)

        return result_df
    
    def get_indicators(self) -> pl.DataFrame:
        """
        Main method to calculate all indicators and return the enhanced DataFrame
        """
        # Calculate all indicators
        self.calculate_indicators()
        
        # Calculate previous values
        result_df = self._calculate_previous_values()
        
        return result_df