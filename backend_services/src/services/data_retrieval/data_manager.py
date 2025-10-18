import asyncio
import logging
import polars as pl
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from .data_providers import DataProviderFactory, BaseDataProvider, AVAILABLE_CRYPTO_ASSETS, TIMEFRAME_MAPPINGS
from ..utils.date_utils import DateUtils

logger = logging.getLogger(__name__)

class DataManager:
    """Handles all data fetching and caching using DataProviderFactory"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.data_cache = {}
        self.data_provider = None

    def __str__(self):
        return f"DataManager(data_provider={self.data_provider})"
        
    async def initialize_provider(self, 
                                  data_provider_name: str, 
                                  user_id: str,
                                  ):
        """Initialize data provider using DataProviderFactory"""
        try:
            # Get user configuration for API keys only
            user_config = await self.db['user_config'].find_one({"user_id": user_id})
            
            if data_provider_name.lower() == 'yahoo':
                self.data_provider = DataProviderFactory.get_provider('yahoo')
                logger.info("Initialized Yahoo Finance data provider")
                
            elif data_provider_name.lower() == 'alpaca':
                if not user_config:
                    logger.warning(f"No user configuration found for user {user_id}, falling back to Yahoo Finance")
                    self.data_provider = DataProviderFactory.get_provider('yahoo')
                    return
                
                # Get API keys from user config
                api_key = user_config.get('alpaca_live_api_key') or user_config.get('alpaca_paper_api_key')
                secret_key = user_config.get('alpaca_live_secret_key') or user_config.get('alpaca_paper_secret_key')
                
                if api_key and secret_key:
                    # Decrypt secret key if needed
                    try:
                        from models.user_config import ConfigEncryption
                        decrypted_secret = ConfigEncryption.decrypt_value(secret_key)
                        logger.info(f"DEBUG DATA MANAGER: Decrypted Alpaca secret key: {decrypted_secret}")
                    except Exception as e:
                        logger.warning(f"Could not decrypt secret key, using as-is: {e}")
                        decrypted_secret = secret_key
                        
                    self.data_provider = DataProviderFactory.get_provider(
                        'alpaca',
                        api_key=api_key,
                        secret_key=decrypted_secret
                    )
                    logger.info("Initialized Alpaca data provider")
                else:
                    logger.warning(f"Alpaca API keys not found for user {user_id}, falling back to Yahoo Finance")
                    self.data_provider = DataProviderFactory.get_provider('yahoo')
                    
            elif data_provider_name.lower() == 'polygon':
                if not user_config:
                    logger.warning(f"No user configuration found for user {user_id}, falling back to Yahoo Finance")
                    self.data_provider = DataProviderFactory.get_provider('yahoo')
                    return
                
                # Get the actual API key (polygon_secret_key), not the key name
                api_key = user_config.get('polygon_secret_key')
                
                if api_key:
                    # Decrypt the API key if needed
                    try:
                        from models.user_config import ConfigEncryption
                        decrypted_api_key = ConfigEncryption.decrypt_value(api_key)
                        logger.info(f"DEBUG DATA MANAGER: Decrypted Polygon API key: {decrypted_api_key}")
                    except Exception as e:
                        logger.warning(f"Could not decrypt Polygon API key, using as-is: {e}")
                        decrypted_api_key = api_key
                    
                    self.data_provider = DataProviderFactory.get_provider('polygon', api_key=decrypted_api_key)
                    logger.info("Initialized Polygon data provider")
                else:
                    logger.warning(f"Polygon API key not found for user {user_id}, falling back to Yahoo Finance")
                    self.data_provider = DataProviderFactory.get_provider('yahoo')
                    
            else:
                logger.warning(f"Unknown data provider '{data_provider_name}', falling back to Yahoo Finance")
                self.data_provider = DataProviderFactory.get_provider('yahoo')
                
        except Exception as e:
            logger.error(f"Error initializing data provider: {e}, falling back to Yahoo Finance")
            self.data_provider = DataProviderFactory.get_provider('yahoo')
    
    async def _fetch_alpaca_data(self, symbols: List[str], start_dt: datetime, end_dt: datetime, timeframe: str) -> List[pl.DataFrame]:
        data = await self.data_provider.get_historical_data(
            symbols=symbols,
            start_date=start_dt,
            end_date=end_dt,
            timeframe=timeframe.strip()
        )
        #logger.info(f"Retrieved data for {symbols}: {data.to_dicts()}")
        #logger.info(f"Retrieved {data.height} data points for {symbols}")
        return [data]

    async def _fetch_yahoo_data(self, symbols: List[str], start_dt: datetime, end_dt: datetime, timeframe: str) -> List[pl.DataFrame]:
        all_data = []
        for symbol in symbols:
            try:
                data = await self.data_provider.get_historical_data(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    timeframe=timeframe.strip()
                )
                
                if isinstance(data, pl.DataFrame) and data.height > 0:
                    if 'symbol' not in data.columns:
                        data = data.with_columns(pl.lit(symbol).alias("symbol"))
                    #logger.info(f"Retrieved data for {symbol}: {data.to_dicts()}")
                    all_data.append(data)
                    #logger.info(f"Retrieved {data.height} data points for {symbol}")
                elif hasattr(data, 'empty') and not data.empty:
                    polars_data = pl.from_pandas(data.reset_index())
                    if 'symbol' not in polars_data.columns:
                        polars_data = polars_data.with_columns(pl.lit(symbol).alias("symbol"))
                    #logger.info(f"Retrieved data for {symbol}: {polars_data.to_dicts()}")
                    all_data.append(polars_data)
                    #logger.info(f"Retrieved {len(data)} data points for {symbol}")
                else:
                    logger.warning(f"No data retrieved for {symbol}")
                    
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                continue
        return all_data

    async def _fetch_polygon_data(self, symbols: List[str], start_dt: datetime, end_dt: datetime, timeframe: str) -> List[pl.DataFrame]:
        all_data = []
        for symbol in symbols:
            try:
                data = await self.data_provider.get_historical_data(
                    symbol=symbol,
                    start_date=start_dt.strftime('%Y-%m-%d'),
                    end_date=end_dt.strftime('%Y-%m-%d'),
                    timeframe=timeframe.strip()
                )
                
                if isinstance(data, pl.DataFrame) and data.height > 0:
                    if 'symbol' not in data.columns:
                        data = data.with_columns(pl.lit(symbol).alias("symbol"))
                    #   logger.info(f"Retrieved data for {symbol}: {data.to_dicts()}")
                    all_data.append(data)
                    #logger.info(f"Retrieved {data.height} data points for {symbol}")
                elif hasattr(data, 'empty') and not data.empty:
                    polars_data = pl.from_pandas(data.reset_index())
                    if 'symbol' not in polars_data.columns:
                        polars_data = polars_data.with_columns(pl.lit(symbol).alias("symbol"))
                    #logger.info(f"Retrieved data for {symbol}: {polars_data.to_dicts()}")
                    all_data.append(polars_data)
                    #logger.info(f"Retrieved {len(data)} data points for {symbol}")
                else:
                    logger.warning(f"No data retrieved for {symbol}")
                    
            except Exception as e:
                logger.error(f"Error fetching data for {symbol}: {e}")
                continue
        return all_data

    def _convert_to_datetime(self, date_str: str) -> datetime:
        """Convert date string to datetime object"""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # Try to parse ISO format
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    
    def _standardize_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        """Standardize column names and ensure required columns exist"""
        if df.height == 0:
            return df
            
        # Standard column mapping
        column_mapping = {
            't': 'datetime',
            'timestamp': 'datetime',
            'time': 'datetime',
            'date': 'datetime'
        }
        
        # Rename columns if they exist
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df = df.rename({old_col: new_col})
        
        # Ensure datetime column exists
        if 'datetime' not in df.columns:
            if df.get_column_index('Date') is not None:
                df = df.rename({'Date': 'datetime'})
            elif hasattr(df, 'index') and isinstance(df.index, pl.datatypes.Datetime):
                # If index is datetime, make it a column
                df = df.with_row_count('datetime')
        
        # Ensure required columns exist with default values
        required_columns = {
            'open': 0.0,
            'high': 0.0,
            'low': 0.0,
            'close': 0.0,
            'volume': 0.0,
            'vwap': 0.0
        }
        
        for col, default_val in required_columns.items():
            if col not in df.columns:
                df = df.with_columns(pl.lit(default_val).alias(col))
        
        return df
    
    def _calculate_lookback_days(self, timeframe: str, limit: int) -> int:
        """Calculate how many days to look back to get enough data points"""
        timeframe
        
        if timeframe in ['1Min', '2Min', '5Min', '15Min', '30Min']:
            # For minute data, assume 6.5 trading hours per day (390 minutes)
            minutes_per_timeframe = int(timeframe.replace('Min', ''))
            points_per_day = 390 / minutes_per_timeframe
            days_needed = max(1, int(limit / points_per_day))
            return days_needed * 2  # Buffer for weekends and holidays
            
        elif timeframe in ['1Hour', '60Min']:
            # For hourly data, assume 6.5 trading hours per day
            points_per_day = 6.5
            days_needed = max(1, int(limit / points_per_day))
            return days_needed * 2
            
        elif timeframe in ['1D', '1DAY']: 
            # For daily data, 1 point per trading day
            return limit * 2  # Buffer for weekends and holidays
            
        elif timeframe in ['1W', '1WK', '1WEEK']:
            # For weekly data
            return limit * 10  # About 10 days per week including weekends
            
        elif timeframe in ['1MO', '1MONTH']:
            # For monthly data
            return limit * 35  # About 35 days per month
            
        else:
            # Default fallback
            return limit * 2
    
    async def fetch_historical_data(self, symbols: List[str], start_date: str, end_date: str, timeframe: str) -> pl.DataFrame:
        """Fetch historical data for symbols using the initialized provider"""
        if not self.data_provider:
            raise ValueError("Data provider not initialized. Call initialize_provider() first.")
        
        
        provider_name = self.data_provider.get_provider_name().lower()
        cache_key = f"{'-'.join(symbols)}_{start_date}_{end_date}_{timeframe}_{provider_name}"
        
        if cache_key in self.data_cache:
            logger.info(f"Using cached data for {symbols}")
            return self.data_cache[cache_key]
        
        logger.info(f"Fetching data for {symbols} from {start_date} to {end_date} using {provider_name}")
        
        try:
            start_dt = self._convert_to_datetime(start_date) if isinstance(start_date, str) else start_date
            end_dt = self._convert_to_datetime(end_date) if isinstance(end_date, str) else end_date
            
            all_data = []

            if provider_name == 'polygon':
                all_data = await self._fetch_polygon_data(symbols, start_dt, end_dt, timeframe)
            elif provider_name == 'alpaca':
                all_data = await self._fetch_alpaca_data(symbols, start_dt, end_dt, timeframe)
            elif provider_name == 'yahoo':
                all_data = await self._fetch_yahoo_data(symbols, start_dt, end_dt, timeframe)
            
            if not all_data:
                logger.warning("No data retrieved for any symbols")
                return pl.DataFrame()
            
            combined_data = pl.concat(all_data, how="vertical")
            combined_data = self._standardize_columns(combined_data)
            
            if 'datetime' in combined_data.columns and 'symbol' in combined_data.columns:
                combined_data = combined_data.sort(["datetime", "symbol"])
            elif 'timestamp' in combined_data.columns and 'symbol' in combined_data.columns:
                combined_data = combined_data.sort(["timestamp", "symbol"])
            
            self.data_cache[cache_key] = combined_data
            logger.info(f"Retrieved {combined_data.height} total data points")
            return combined_data
            
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            raise
    
    async def fetch_data(self, symbols: List[str], timeframe: str, limit: int, data_provider: str) -> pl.DataFrame:
        """
        Fetches the latest market data for a set of symbols, up to a specified limit.

        This function calculates a suitable start date to ensure enough data is retrieved
        to satisfy the limit, accounting for non-trading days.
        """
        if not self.data_provider:
            raise ValueError("Data provider not initialized. Call initialize_provider() first.")
        
        logger.info(f"Fetching latest {limit} data points for {symbols} with timeframe {timeframe} using {data_provider}")

        end_date = datetime.now()

        # Get the timeframe category and calculate lookback period
        days_to_look_back = self._calculate_lookback_days(timeframe, limit)
        logger.info(f"Data Manager DEBUG: Days to look back: {days_to_look_back}")

        start_date = end_date - timedelta(days=max(1, days_to_look_back))
        logger.info(f"Data Manager DEBUG: Start date: {start_date}")
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        symbols = [symbol.upper() for symbol in symbols]

        try:
            historical_data = await self.fetch_historical_data(
                    symbols=symbols,
                    start_date=start_date_str,
                    end_date=end_date_str,
                    timeframe=timeframe.strip() 
                )

            if historical_data.height == 0:
                return historical_data

            # Ensure we only return the last `limit` data points per symbol
            if 'symbol' in historical_data.columns:
                final_data = historical_data.group_by('symbol', maintain_order=True).tail(limit)
            else:
                # If no symbol column, just take the last limit rows
                final_data = historical_data.tail(limit)

            logger.info(f"Final data returned by fetch_data for {symbols}: {final_data.to_dicts()}")
            return final_data

        except Exception as e:
            logger.error(f"Failed to fetch latest market data: {e}")
            # Return an empty DataFrame on failure to prevent crashes downstream
            return pl.DataFrame()