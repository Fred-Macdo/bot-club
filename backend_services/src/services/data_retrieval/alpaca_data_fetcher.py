from datetime import datetime, timedelta, timezone
import polars as pl
import requests
import json
import aiohttp
import asyncio

from typing import Optional, Union, Dict, Any, List, Literal

class AlpacaDataFetcher:
    def __init__(self, api_key: str, secret_key: str, base_url: str):
        """Initialize AlpacaDataFetcher with API credentials
        
        Parameters:
            - api_key: Alpaca API key
            - secret_key: Alpaca API secret key
            
        Returns:
            - Returns an instance of AlpacaDataFetcher client
            
        """

        self.headers = {
            "accept": "application/json",
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key
        }
        self.payload = {}
        self.base_url = base_url

        self.timeframe_map = [
            "1Min",
            "5Min",
            "15Min", 
            "30Min",
            "1H",
            "1D",
            "1W",
            "1M"
        ]

    def _format_crypto_symbol(self, symbol: str) -> str:
        """Convert crypto symbol to correct format"""
        if symbol.endswith('USDT'):
            return f"{symbol[:-4]}/USD"
        elif symbol.endswith('USD'):
            return f"{symbol[:-3]}/USD"
        return symbol
    
    def _process_raw_bars_to_df(self, bars_data):
        df = pl.DataFrame(bars_data)
        df['t'] = pl.to_datetime(df['t'])
        df = df.rename(columns={
            't': 'timestamp',
            'o': 'open',
            'h': 'high', 
            'l': 'low',
            'c': 'close',
            'v': 'volume',
            'n': 'trades',
            'vw': 'vwap'
        })
        return df

    async def get_account(self) -> Dict[str, Any]:
        """Get account information"""
        url = f"{self.base_url}/account"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to get account: {response.status}")

    async def get_positions(self) -> Dict[str, Any]:
        """Get current positions"""
        url = f"{self.base_url}/positions"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    positions = await response.json()
                    # Convert to symbol -> position mapping
                    return {pos['symbol']: pos for pos in positions}
                else:
                    return {}

    async def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        type: str,
        time_in_force: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Dict[str, Any]:
        """Place an order"""
        url = f"{self.base_url}/orders"
        
        order_data = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": type,
            "time_in_force": time_in_force
        }
        
        # Add stop loss and take profit if provided
        if stop_loss:
            order_data["stop_loss"] = {"stop_price": str(stop_loss)}
        if take_profit:
            order_data["take_profit"] = {"limit_price": str(take_profit)}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=order_data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"Failed to place order: {response.status} - {error_text}")

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order"""
        url = f"{self.base_url}/orders/{order_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to cancel order: {response.status}")

    async def get_orders(self, status: str = "open") -> List[Dict[str, Any]]:
        """Get orders with specified status"""
        url = f"{self.base_url}/orders?status={status}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return []

    def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10000
    ) -> pl.DataFrame:
        """
        Fetch historical OHLCV data from Alpaca
        
        Parameters:
        - symbol: Trading symbol (e.g., 'BTC/USD' for crypto, 'AAPL' for stocks)
        - timeframe: Time interval ('1m', '5m', '15m', '1h', '1d')
        - start_date: Start date for historical data (defaults to 100 bars before end_date)
        - end_date: End date for historical data (defaults to now)
        - limit: Maximum number of bars to fetch
        
        Returns:
        - polars DataFrame with OHLCVW data
        """
        # Set default end date to now if not provided
        if end_date in [None, '']:
            end_date = datetime.now(timezone(timedelta(hours=-5)))
        
        # Set default start date if not provided
        if start_date in [None, '']: 
            start_date = datetime.now(timezone(timedelta(hours=-5))) - timedelta(days=30)

        # Ensure dates are timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=datetime.timezone.utc)
            
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=datetime.timezone.utc)

        # Determine if it's a crypto symbol and format accordingly
        check_if_crypto = symbol.endswith('USD') or symbol.endswith('USDT') or '/' in symbol
        if check_if_crypto:
            symbol = self._format_crypto_symbol(symbol)
            is_crypto = True

        if timeframe in self.timeframe_map:
            if is_crypto:
                url = "https://data.alpaca.markets/v1beta3/crypto/us/bars?"
                self.payload = {
                    "symbols": symbol,
                    "timeframe": timeframe,
                    "start": start_date.strftime("%Y-%m-%d"),
                    "end": end_date.strftime("%Y-%m-%d"),
                    "limit": limit,
                    "feed": 'iex'
                }
                
            else:
                
                    # construct api payload request.
                    url = "https://data.alpaca.markets/v2/stocks/bars?"
                    self.payload = {
                        "symbols": ','.join(symbol),
                        "timeframe": timeframe,
                        "start": start_date.strftime("%Y-%m-%d"),
                        "end": end_date.strftime("%Y-%m-%d"),
                        "limit":limit,
                        "feed": 'iex'
                        }
                # format the bars alpaca api response into a dataframe
            response = requests.get(url, headers=self.headers, params=self.payload)
            data = response.json()
            print(data)
            dfs = []
            for symbol, bars in data['bars'].items():
                symbol_df = self._process_raw_bars_to_df(bars)
                symbol_df['symbol'] = symbol  # Add symbol here instead
                dfs.append(symbol_df)

                # Combine all symbols into one DataFrame
                final_df = pl.concat(dfs, axis=0)
                final_df = final_df.set_index(['timestamp', 'symbol'])

                return response, final_df


    def get_latest_quote(self, symbol: str) -> Dict[str, float]:
        """Get the latest quote for a symbol"""
        
        is_crypto = symbol.endswith('USD') or symbol.endswith('USDT') or '/' in symbol
        if is_crypto:
            symbol = self._format_crypto_symbol(symbol)
            quote = self.trading_client.get_crypto_quote(symbol)
        else:
            quote = self.trading_client.get_latest_quote(symbol)
            
        return {
            'bid': float(quote.bid_price),
            'ask': float(quote.ask_price),
            'timestamp': quote.timestamp
        }


    def get_account_balance(self) -> float:
        """Get current account balance"""
        try:
            account = self.trading_client.get_account()
            return float(account.cash)
        except Exception as e:
            raise Exception(f"Error getting account balance: {str(e)}")