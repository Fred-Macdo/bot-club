import requests
import json
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import requests
import asyncio
from enum import Enum
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..utils.enums import TradingMode

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Environment(Enum):
    PAPER = "https://paper-api.alpaca.markets"
    LIVE = "https://api.alpaca.markets"

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"

class TimeInForce(Enum):
    DAY = "day"
    GTC = "gtc"  # Good Till Canceled
    IOC = "ioc"  # Immediate or Cancel
    FOK = "fok"  # Fill or Kill

@dataclass
class Position:
    symbol: str
    qty: Decimal
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal
    unrealized_plpc: Decimal
    current_price: Decimal
    lastday_price: Decimal
    change_today: Decimal
    
    @classmethod
    def from_alpaca_response(cls, data: dict) -> 'Position':
        return cls(
            symbol=data['symbol'],
            qty=Decimal(data['qty']),
            market_value=Decimal(data['market_value']),
            cost_basis=Decimal(data['cost_basis']),
            unrealized_pl=Decimal(data['unrealized_pl']),
            unrealized_plpc=Decimal(data['unrealized_plpc']),
            current_price=Decimal(data['current_price']),
            lastday_price=Decimal(data['lastday_price']),
            change_today=Decimal(data['change_today'])
        )

@dataclass
class Order:
    id: str
    symbol: str
    qty: Decimal
    side: str
    order_type: str
    time_in_force: str
    status: str
    filled_qty: Decimal
    filled_avg_price: Optional[Decimal]
    limit_price: Optional[Decimal]
    stop_price: Optional[Decimal]
    created_at: datetime
    updated_at: datetime
    
    @classmethod
    def from_alpaca_response(cls, data: dict) -> 'Order':
        return cls(
            id=data['id'],
            symbol=data['symbol'],
            qty=Decimal(data['qty']),
            side=data['side'],
            order_type=data['order_type'],
            time_in_force=data['time_in_force'],
            status=data['status'],
            filled_qty=Decimal(data['filled_qty']),
            filled_avg_price=Decimal(data['filled_avg_price']) if data.get('filled_avg_price') else None,
            limit_price=Decimal(data['limit_price']) if data.get('limit_price') else None,
            stop_price=Decimal(data['stop_price']) if data.get('stop_price') else None,
            created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
        )

@dataclass
class Account:
    id: str
    account_number: str
    status: str
    currency: str
    buying_power: Decimal
    regt_buying_power: Decimal
    daytrading_buying_power: Decimal
    cash: Decimal
    portfolio_value: Decimal
    equity: Decimal
    last_equity: Decimal
    multiplier: str
    created_at: datetime
    
    @classmethod
    def from_alpaca_response(cls, data: dict) -> 'Account':
        return cls(
            id=data['id'],
            account_number=data['account_number'],
            status=data['status'],
            currency=data['currency'],
            buying_power=Decimal(data['buying_power']),
            regt_buying_power=Decimal(data['regt_buying_power']),
            daytrading_buying_power=Decimal(data['daytrading_buying_power']),
            cash=Decimal(data['cash']),
            portfolio_value=Decimal(data['portfolio_value']),
            equity=Decimal(data['equity']),
            last_equity=Decimal(data['last_equity']),
            multiplier=data['multiplier'],
            created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
        )

class AlpacaAPIException(Exception):
    """Custom exception for Alpaca API errors"""
    def __init__(self, message: str, status_code: int = None, response_data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

class AlpacaTradingService:
    def __init__(self, db, user_id, mode, strategy_id):
        self.db = db
        self.user_id = user_id
        self.mode = mode
        self.strategy_id = strategy_id
        self.executor = None

    async def run(self, strategy: dict):
        # Implementation of trading logic will go here
        # This will likely involve a loop that fetches data, checks the strategy, and places trades.
        print(f"Running {self.mode.value} trading for strategy {self.strategy_id} for user {self.user_id}")
        # For now, just a placeholder print
        await asyncio.sleep(10) # Placeholder for long-running task
        print("Trading session finished.")


class AlpacaPortfolioManager:
    """
    Comprehensive Portfolio Manager for Alpaca REST API
    
    Handles authentication, position management, order execution, and portfolio analytics.
    Designed to integrate with FastAPI backend and MongoDB for persistence.
    """
    
    def __init__(self, 
                 api_key: str, 
                 secret_key: str, 
                 environment: Environment = Environment.PAPER, 
                 db: AsyncIOMotorDatabase = None, 
                 user_id: str = None, 
                 mode: TradingMode = TradingMode.BACKTEST):
        """
        Initialize Portfolio Manager
        
        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key  
            environment: Trading environment (PAPER or LIVE)
        """
        self.db = db
        self.user_id = user_id
        self.mode = mode
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = environment.value
        self.session = requests.Session()
        
        # Set authentication headers
        self.session.headers.update({
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.secret_key,
            'Content-Type': 'application/json'
        })
        
        # Cache for positions and account data
        self._positions_cache: Dict[str, Position] = {}
        self._account_cache: Optional[Account] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=30)  # 30 second cache TTL
        
        # Validate connection on initialization
        self._validate_connection()
    
    def _validate_connection(self) -> bool:
        """Validate API connection and credentials"""
        try:
            response = self._make_request('GET', '/v2/account')
            logger.info("Successfully connected to Alpaca API")
            return True
        except AlpacaAPIException as e:
            logger.error(f"Failed to connect to Alpaca API: {e}")
            raise
    
    def _make_request(self, method: str, endpoint: str, params: dict = None, data: dict = None) -> dict:
        """
        Make HTTP request to Alpaca API with error handling
        
        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Request body data
            
        Returns:
            Parsed JSON response
            
        Raises:
            AlpacaAPIException: For API errors or network issues
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data, params=params)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, params=params)
            elif method.upper() == 'PATCH':
                response = self.session.patch(url, json=data, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("Rate limit exceeded, waiting before retry")
                raise AlpacaAPIException("Rate limit exceeded", 429, response.json())
            
            # Raise exception for HTTP errors
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise AlpacaAPIException(f"Request failed: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise AlpacaAPIException(f"Invalid JSON response: {str(e)}")
    
    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid"""
        if not self._cache_timestamp:
            return False
        return datetime.now() - self._cache_timestamp < self._cache_ttl
    
    def get_account(self, use_cache: bool = True) -> Account:
        """
        Get account information
        
        Args:
            use_cache: Whether to use cached data if available
            
        Returns:
            Account object with current account information
        """
        if use_cache and self._account_cache and self._is_cache_valid():
            return self._account_cache
        
        response = self._make_request('GET', '/v2/account')
        account = Account.from_alpaca_response(response)
        
        # Update cache
        self._account_cache = account
        self._cache_timestamp = datetime.now()
        
        return account
    
    def get_positions(self, use_cache: bool = True) -> Dict[str, Position]:
        """
        Get all current positions
        
        Args:
            use_cache: Whether to use cached data if available
            
        Returns:
            Dictionary mapping symbol to Position object
        """
        if use_cache and self._positions_cache and self._is_cache_valid():
            return self._positions_cache.copy()
        
        response = self._make_request('GET', '/v2/positions')
        positions = {}
        
        for pos_data in response:
            position = Position.from_alpaca_response(pos_data)
            positions[position.symbol] = position
        
        # Update cache
        self._positions_cache = positions
        if not self._cache_timestamp:  # Only update timestamp if not set by account call
            self._cache_timestamp = datetime.now()
        
        return positions.copy()
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for specific symbol
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            
        Returns:
            Position object or None if no position exists
        """
        try:
            response = self._make_request('GET', f'/v2/positions/{symbol}')
            return Position.from_alpaca_response(response)
        except AlpacaAPIException as e:
            if e.status_code == 404:
                return None
            raise
    
    def submit_order(self, 
                    symbol: str, 
                    qty: Union[int, Decimal], 
                    side: OrderSide, 
                    order_type: OrderType,
                    time_in_force: TimeInForce = TimeInForce.DAY,
                    limit_price: Optional[Decimal] = None,
                    stop_price: Optional[Decimal] = None,
                    trail_price: Optional[Decimal] = None,
                    trail_percent: Optional[Decimal] = None) -> Order:
        """
        Submit an order
        
        Args:
            symbol: Stock symbol
            qty: Quantity to buy/sell
            side: Buy or sell
            order_type: Order type (market, limit, etc.)
            time_in_force: How long order remains active
            limit_price: Limit price for limit orders
            stop_price: Stop price for stop orders
            trail_price: Trail amount for trailing stop orders
            trail_percent: Trail percentage for trailing stop orders
            
        Returns:
            Order object with order details
        """
        order_data = {
            'symbol': symbol,
            'qty': str(qty),
            'side': side.value,
            'type': order_type.value,
            'time_in_force': time_in_force.value
        }
        
        # Add price parameters based on order type
        if limit_price is not None:
            order_data['limit_price'] = str(limit_price)
        if stop_price is not None:
            order_data['stop_price'] = str(stop_price)
        if trail_price is not None:
            order_data['trail_price'] = str(trail_price)
        if trail_percent is not None:
            order_data['trail_percent'] = str(trail_percent)
        
        response = self._make_request('POST', '/v2/orders', data=order_data)
        order = Order.from_alpaca_response(response)
        
        logger.info(f"Submitted order: {side.value} {qty} {symbol} at {order_type.value}")
        
        # Invalidate cache since portfolio state may have changed
        self._cache_timestamp = None
        
        return order
    
    def get_orders(self, status: str = 'open', limit: int = 50) -> List[Order]:
        """
        Get orders with optional filtering
        
        Args:
            status: Order status filter ('open', 'closed', 'all')
            limit: Maximum number of orders to return
            
        Returns:
            List of Order objects
        """
        params = {
            'status': status,
            'limit': limit,
            'direction': 'desc'  # Most recent first
        }
        
        response = self._make_request('GET', '/v2/orders', params=params)
        return [Order.from_alpaca_response(order_data) for order_data in response]
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get specific order by ID
        
        Args:
            order_id: Alpaca order ID
            
        Returns:
            Order object or None if not found
        """
        try:
            response = self._make_request('GET', f'/v2/orders/{order_id}')
            return Order.from_alpaca_response(response)
        except AlpacaAPIException as e:
            if e.status_code == 404:
                return None
            raise
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order
        
        Args:
            order_id: Alpaca order ID
            
        Returns:
            True if successfully canceled
        """
        try:
            self._make_request('DELETE', f'/v2/orders/{order_id}')
            logger.info(f"Canceled order: {order_id}")
            return True
        except AlpacaAPIException as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders
        
        Returns:
            True if all orders were canceled successfully
        """
        try:
            response = self._make_request('DELETE', '/v2/orders')
            canceled_count = len(response)
            logger.info(f"Canceled {canceled_count} orders")
            return True
        except AlpacaAPIException as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False
    
    def close_position(self, symbol: str, qty: Optional[Union[int, Decimal]] = None) -> Optional[Order]:
        """
        Close a position (full or partial)
        
        Args:
            symbol: Stock symbol
            qty: Quantity to close (None for full position)
            
        Returns:
            Order object for the closing order
        """
        position = self.get_position(symbol)
        if not position:
            logger.warning(f"No position found for {symbol}")
            return None
        
        if qty is None:
            qty = abs(position.qty)  # Close full position
        
        # Determine side based on current position
        side = OrderSide.SELL if position.qty > 0 else OrderSide.BUY
        
        return self.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=OrderType.MARKET
        )
    
    def close_all_positions(self) -> List[Order]:
        """
        Close all open positions
        
        Returns:
            List of closing orders
        """
        positions = self.get_positions(use_cache=False)  # Get fresh data
        closing_orders = []
        
        for symbol, position in positions.items():
            try:
                order = self.close_position(symbol)
                if order:
                    closing_orders.append(order)
            except Exception as e:
                logger.error(f"Failed to close position {symbol}: {e}")
        
        return closing_orders
    
    def get_portfolio_summary(self) -> dict:
        """
        Get comprehensive portfolio summary
        
        Returns:
            Dictionary with portfolio metrics and analysis
        """
        account = self.get_account(use_cache=False)
        positions = self.get_positions(use_cache=False)
        
        # Calculate portfolio metrics
        total_positions = len(positions)
        total_market_value = sum(pos.market_value for pos in positions.values())
        total_unrealized_pl = sum(pos.unrealized_pl for pos in positions.values())
        total_cost_basis = sum(pos.cost_basis for pos in positions.values())
        
        # Calculate allocation percentages
        allocations = {}
        if total_market_value > 0:
            for symbol, position in positions.items():
                allocations[symbol] = float(position.market_value / total_market_value * 100)
        
        # Top gainers and losers
        sorted_positions = sorted(positions.values(), key=lambda x: x.unrealized_plpc, reverse=True)
        top_gainers = [(pos.symbol, float(pos.unrealized_plpc)) for pos in sorted_positions[:3]]
        top_losers = [(pos.symbol, float(pos.unrealized_plpc)) for pos in sorted_positions[-3:]]
        
        return {
            'account_value': float(account.portfolio_value),
            'buying_power': float(account.buying_power),
            'cash': float(account.cash),
            'total_positions': total_positions,
            'total_market_value': float(total_market_value),
            'total_unrealized_pl': float(total_unrealized_pl),
            'total_cost_basis': float(total_cost_basis),
            'total_return_pct': float(total_unrealized_pl / total_cost_basis * 100) if total_cost_basis > 0 else 0,
            'allocations': allocations,
            'top_gainers': top_gainers,
            'top_losers': top_losers,
            'day_change': float(account.equity - account.last_equity),
            'day_change_pct': float((account.equity - account.last_equity) / account.last_equity * 100) if account.last_equity > 0 else 0
        }
    
    def get_buying_power_for_symbol(self, symbol: str, price: Decimal) -> Decimal:
        """
        Calculate maximum shares that can be purchased for a symbol
        
        Args:
            symbol: Stock symbol
            price: Current stock price
            
        Returns:
            Maximum quantity that can be purchased
        """
        account = self.get_account()
        return account.buying_power // price
    
    def calculate_position_size(self, symbol: str, price: Decimal, risk_percent: float = 2.0) -> Decimal:
        """
        Calculate position size based on risk management rules
        
        Args:
            symbol: Stock symbol
            price: Entry price
            risk_percent: Maximum risk as percentage of portfolio
            
        Returns:
            Recommended position size
        """
        account = self.get_account()
        portfolio_value = account.portfolio_value
        
        # Calculate maximum risk amount
        max_risk_amount = portfolio_value * Decimal(risk_percent / 100)
        
        # For simplicity, assume 2% stop loss (can be made configurable)
        stop_loss_percent = Decimal('0.02')
        risk_per_share = price * stop_loss_percent
        
        if risk_per_share > 0:
            max_shares = max_risk_amount / risk_per_share
            # Also consider buying power
            max_shares_by_bp = self.get_buying_power_for_symbol(symbol, price)
            return min(max_shares, max_shares_by_bp)
        
        return Decimal('0')
    
    def refresh_cache(self):
        """Force refresh of cached data"""
        self._cache_timestamp = None
        self._positions_cache.clear()
        self._account_cache = None
        
        # Pre-load fresh data
        self.get_account(use_cache=False)
        self.get_positions(use_cache=False)
    
    def get_health_check(self) -> dict:
        """
        Perform health check of the portfolio manager
        
        Returns:
            Dictionary with system status and metrics
        """
        try:
            account = self.get_account(use_cache=False)
            positions_count = len(self.get_positions(use_cache=False))
            open_orders = len(self.get_orders(status='open'))
            
            return {
                'status': 'healthy',
                'account_status': account.status,
                'positions_count': positions_count,
                'open_orders_count': open_orders,
                'buying_power': float(account.buying_power),
                'portfolio_value': float(account.portfolio_value),
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'last_updated': datetime.now().isoformat()
            }
