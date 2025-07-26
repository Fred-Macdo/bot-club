import React, { useState, useEffect } from 'react';
import {
  Paper,
  Typography,
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  IconButton,
  TextField,
  Button,
  Chip,
  useTheme,
  Alert,
  CircularProgress,
  InputAdornment,
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Search as SearchIcon,
} from '@mui/icons-material';
import { useAlpaca } from '../../context/AlpacaContext';
import { isMarketHours } from '../../utils/dateUtils'; // Import the new utility

const Watchlist = () => {
  const theme = useTheme();
  const { paperConfig, liveConfig, isAlpacaConfigured } = useAlpaca();
  
  // Default watchlist with major indices and popular stocks
  const defaultWatchlist = [
    'SPY',   // S&P 500 ETF
    'QQQ',   // Nasdaq 100 ETF
    'IWM',   // Russell 2000 ETF
    'VTI',   // Total Stock Market ETF
    'DIA',   // Dow Jones ETF
    'AAPL',  // Apple
    'MSFT',  // Microsoft
    'GOOGL', // Google
    'AMZN',  // Amazon
    'TSLA',  // Tesla
  ];

  const [watchlist, setWatchlist] = useState(defaultWatchlist);
  const [newSymbol, setNewSymbol] = useState('');
  const [stockData, setStockData] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  
  // Sorting states
  const [orderBy, setOrderBy] = useState('symbol');
  const [order, setOrder] = useState('asc');

  // Handle sort request
  const handleRequestSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
  };

  // Sort function
  const sortData = (array, comparator) => {
    const stabilizedThis = array.map((el, index) => [el, index]);
    stabilizedThis.sort((a, b) => {
      const order = comparator(a[0], b[0]);
      if (order !== 0) return order;
      return a[1] - b[1];
    });
    return stabilizedThis.map((el) => el[0]);
  };

  // Comparator function
  const getComparator = (order, orderBy) => {
    return order === 'desc'
      ? (a, b) => descendingComparator(a, b, orderBy)
      : (a, b) => -descendingComparator(a, b, orderBy);
  };

  const descendingComparator = (a, b, orderBy) => {
    const aData = stockData[a] || {};
    const bData = stockData[b] || {};
    
    switch (orderBy) {
      case 'symbol':
        return b.localeCompare(a);
      case 'price':
        return (bData.price || 0) - (aData.price || 0);
      case 'change':
        return (bData.change || 0) - (aData.change || 0);
      case 'changePercent':
        return (bData.changePercent || 0) - (aData.changePercent || 0);
      case 'volume':
        return (bData.volume || 0) - (aData.volume || 0);
      default:
        return 0;
    }
  };

  // Fetch stock prices from Alpaca
  const fetchStockPrices = async () => {
    if (!isAlpacaConfigured) return;
    
    setLoading(true);
    setError(null);
    
    // Use paper config if available, otherwise live config
    const config = paperConfig || liveConfig;
    if (!config) {
      setError('No API configuration available');
      setLoading(false);
      return;
    }

    const headers = {
      'APCA-API-KEY-ID': config.key,
      'APCA-API-SECRET-KEY': config.secret,
    };

    try {
      // Get current date and previous trading day for comparison
      const now = new Date();
      const previousDay = new Date(now);
      previousDay.setDate(now.getDate() - 1);
      
      const currentDate = now.toISOString().split('T')[0];
      const prevDate = previousDay.toISOString().split('T')[0];

      // Fetch latest quotes and previous close data
      const symbolsParam = watchlist.join(',');
      
      // Get latest quotes
      const quotesResponse = await fetch(
        `${config.endpoint}/v2/stocks/quotes/latest?symbols=${symbolsParam}`,
        { headers }
      );

      // Get previous close data for comparison
      const barsResponse = await fetch(
        `${config.endpoint}/v2/stocks/bars?symbols=${symbolsParam}&timeframe=1Day&start=${prevDate}&end=${currentDate}&limit=2`,
        { headers }
      );

      if (!quotesResponse.ok) {
        throw new Error(`Quotes API error! status: ${quotesResponse.status}`);
      }

      if (!barsResponse.ok) {
        throw new Error(`Bars API error! status: ${barsResponse.status}`);
      }

      const quotesData = await quotesResponse.json();
      const barsData = await barsResponse.json();
      
      if (quotesData.quotes) {
        const newStockData = {};
        
        // Process each symbol's data
        Object.entries(quotesData.quotes).forEach(([symbol, quote]) => {
          if (quote) {
            // Get current price from quote
            const currentPrice = quote.ap || quote.bp || quote.mp || 0; // Ask, bid, or mid price
            
            // Get previous close from bars data
            let previousClose = 0;
            if (barsData.bars && barsData.bars[symbol] && barsData.bars[symbol].length > 0) {
              // Get the most recent bar's close price
              const bars = barsData.bars[symbol];
              previousClose = bars[bars.length - 1].c || 0;
            }
            
            // Calculate change
            const change = previousClose !== 0 ? currentPrice - previousClose : 0;
            const changePercent = previousClose !== 0 ? (change / previousClose) * 100 : 0;
            
            newStockData[symbol] = {
              price: currentPrice,
              change: change,
              changePercent: changePercent,
              volume: quote.as || quote.bs || 0, // Ask size or bid size
              previousClose: previousClose,
              timestamp: quote.t,
              bid: quote.bp || 0,
              ask: quote.ap || 0,
              bidSize: quote.bs || 0,
              askSize: quote.as || 0,
            };
          }
        });
        
        setStockData(newStockData);
        setLastUpdate(new Date());
      }
    } catch (err) {
      console.error('Error fetching stock prices:', err);
      setError(`Failed to fetch stock prices: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Alternative method using snapshots (if quotes don't work well)
  const fetchStockSnapshots = async () => {
    if (!isAlpacaConfigured) return;
    
    setLoading(true);
    setError(null);
    
    const config = paperConfig || liveConfig;
    if (!config) {
      setError('No API configuration available');
      setLoading(false);
      return;
    }

    const headers = {
      'APCA-API-KEY-ID': config.key,
      'APCA-API-SECRET-KEY': config.secret,
    };

    // Use the correct data endpoint
    const dataApiEndpoint = 'https://data.alpaca.markets';

    try {
      // Fetch snapshots for all symbols
      const symbolsParam = watchlist.join(',');
      const response = await fetch(
        `${dataApiEndpoint}/v2/stocks/snapshots?symbols=${symbolsParam}`,
        { headers }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      
      if (data && data[Object.keys(data)[0]]) {
        const newStockData = {};
        
        // Process each symbol's snapshot data
        Object.entries(data).forEach(([symbol, snapshot]) => {
          if (snapshot && snapshot.latestQuote) {
            const quote = snapshot.latestQuote;
            const dailyBar = snapshot.dailyBar;
            const prevDailyBar = snapshot.prevDailyBar;
            
            // Get current price and previous close
            const currentPrice = quote.ap || quote.bp || (dailyBar ? dailyBar.c : 0);
            const previousClose = prevDailyBar ? prevDailyBar.c : (dailyBar ? dailyBar.o : 0);
            
            // Calculate change
            const change = previousClose !== 0 ? currentPrice - previousClose : 0;
            const changePercent = previousClose !== 0 ? (change / previousClose) * 100 : 0;
            
            newStockData[symbol] = {
              price: currentPrice,
              change: change,
              changePercent: changePercent,
              volume: dailyBar ? dailyBar.v : 0,
              previousClose: previousClose,
              timestamp: quote.t,
              bid: quote.bp || 0,
              ask: quote.ap || 0,
              bidSize: quote.bs || 0,
              askSize: quote.as || 0,
              high: dailyBar ? dailyBar.h : 0,
              low: dailyBar ? dailyBar.l : 0,
              open: dailyBar ? dailyBar.o : 0,
            };
          }
        });
        
        setStockData(newStockData);
        setLastUpdate(new Date());
      }
    } catch (err) {
      console.error('Error fetching stock snapshots:', err);
      setError(`Failed to fetch stock prices: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Add new symbol to watchlist
  const addSymbol = () => {
    const symbol = newSymbol.trim().toUpperCase();
    if (symbol && !watchlist.includes(symbol)) {
      setWatchlist([...watchlist, symbol]);
      setNewSymbol('');
    }
  };

  // Remove symbol from watchlist
  const removeSymbol = (symbol) => {
    setWatchlist(watchlist.filter(s => s !== symbol));
    const newStockData = { ...stockData };
    delete newStockData[symbol];
    setStockData(newStockData);
  };

  // Handle Enter key press in input field
  const handleKeyPress = (event) => {
    if (event.key === 'Enter') {
      addSymbol();
    }
  };

  // Format price display
  const formatPrice = (price) => {
    return price ? `$${price.toFixed(2)}` : 'N/A';
  };

  // Format change display
  const formatChange = (change, changePercent) => {
    if (!change && !changePercent) return 'N/A';
    const sign = change >= 0 ? '+' : '';
    return `${sign}${change.toFixed(2)} (${sign}${changePercent.toFixed(2)}%)`;
  };

  // Get color for price change
  const getChangeColor = (change) => {
    if (change > 0) return theme.palette.success.main;
    if (change < 0) return theme.palette.error.main;
    return theme.palette.text.secondary;
  };

  // Fetch data on component mount and when watchlist changes
  useEffect(() => {
    if (isAlpacaConfigured && watchlist.length > 0) {
      // Try snapshots first, fall back to quotes if needed
      fetchStockSnapshots();
    }
  }, [watchlist, isAlpacaConfigured]);

  // Set up auto-refresh
  useEffect(() => {
    if (!isAlpacaConfigured) return;
    
    // Check market hours and set interval accordingly
    if (isMarketHours()) {
      const interval = setInterval(() => {
        fetchStockSnapshots();
      }, 10000); // Refresh every 10 seconds during market hours

      return () => clearInterval(interval);
    } else {
      // Optional: Fetch once when component mounts outside market hours
      fetchStockSnapshots();
    }
  }, [watchlist, isAlpacaConfigured]);

  // Get sorted watchlist
  const sortedWatchlist = sortData(watchlist, getComparator(order, orderBy));

  if (!isAlpacaConfigured) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Watchlist
        </Typography>
        <Alert severity="info">
          Configure your Alpaca API keys to view real-time stock prices.
        </Alert>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 3, borderRadius: 2, height: '500px', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6">
          Watchlist
        </Typography>
        {lastUpdate && (
          <Typography variant="caption" color="text.secondary">
            Last updated: {lastUpdate.toLocaleTimeString()}
          </Typography>
        )}
      </Box>

      {/* Add Symbol Input */}
      <Box sx={{ display: 'flex', gap: 1, mb: 3 }}>
        <TextField
          size="small"
          placeholder="Add symbol (e.g., AAPL)"
          value={newSymbol}
          onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
          onKeyPress={handleKeyPress}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          sx={{ flexGrow: 1 }}
        />
        <Button
          variant="contained"
          onClick={addSymbol}
          startIcon={<AddIcon />}
          disabled={!newSymbol.trim()}
        >
          Add
        </Button>
      </Box>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Watchlist Table */}
      <TableContainer sx={{ flexGrow: 1, maxHeight: 'none' }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell sortDirection={orderBy === 'symbol' ? order : false}>
                <TableSortLabel
                  active={orderBy === 'symbol'}
                  direction={orderBy === 'symbol' ? order : 'asc'}
                  onClick={() => handleRequestSort('symbol')}
                >
                  Symbol
                </TableSortLabel>
              </TableCell>
              <TableCell align="right" sortDirection={orderBy === 'price' ? order : false}>
                <TableSortLabel
                  active={orderBy === 'price'}
                  direction={orderBy === 'price' ? order : 'asc'}
                  onClick={() => handleRequestSort('price')}
                >
                  Price
                </TableSortLabel>
              </TableCell>
              <TableCell align="right" sortDirection={orderBy === 'changePercent' ? order : false}>
                <TableSortLabel
                  active={orderBy === 'changePercent'}
                  direction={orderBy === 'changePercent' ? order : 'asc'}
                  onClick={() => handleRequestSort('changePercent')}
                >
                  Change
                </TableSortLabel>
              </TableCell>
              <TableCell align="right" sortDirection={orderBy === 'volume' ? order : false}>
                <TableSortLabel
                  active={orderBy === 'volume'}
                  direction={orderBy === 'volume' ? order : 'asc'}
                  onClick={() => handleRequestSort('volume')}
                >
                  Volume
                </TableSortLabel>
              </TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedWatchlist.map((symbol) => {
              const data = stockData[symbol];
              const isPositive = data?.change >= 0;
              
              return (
                <TableRow
                  key={symbol}
                  sx={{
                    '&:nth-of-type(odd)': { bgcolor: theme.palette.action.hover },
                    '&:hover': { bgcolor: theme.palette.action.selected }
                  }}
                >
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Chip
                        label={symbol}
                        size="small"
                        sx={{
                          bgcolor: theme.palette.primary.light,
                          color: theme.palette.primary.contrastText,
                          fontWeight: 'bold'
                        }}
                      />
                      {data && data.change !== 0 && (
                        isPositive ? (
                          <TrendingUpIcon sx={{ color: theme.palette.success.main, fontSize: 16 }} />
                        ) : (
                          <TrendingDownIcon sx={{ color: theme.palette.error.main, fontSize: 16 }} />
                        )
                      )}
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                      {data ? formatPrice(data.price) : (loading ? '...' : 'N/A')}
                    </Typography>
                    {data && data.bid && data.ask && (
                      <Typography variant="caption" color="text.secondary" display="block">
                        {data.bid.toFixed(2)} x {data.ask.toFixed(2)}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <Typography
                      variant="body2"
                      sx={{
                        color: data ? getChangeColor(data.change) : theme.palette.text.secondary,
                        fontWeight: 'bold'
                      }}
                    >
                      {data ? formatChange(data.change, data.changePercent) : (loading ? '...' : 'N/A')}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2">
                      {data && data.volume ? data.volume.toLocaleString() : 'N/A'}
                    </Typography>
                  </TableCell>
                  <TableCell align="center">
                    <IconButton
                      size="small"
                      onClick={() => removeSymbol(symbol)}
                      sx={{ color: theme.palette.error.main }}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Loading Indicator */}
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
          <CircularProgress size={24} />
        </Box>
      )}

      {/* Refresh Button */}
      <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
        <Button
          variant="outlined"
          onClick={fetchStockSnapshots}
          disabled={loading}
          size="small"
        >
          {loading ? 'Refreshing...' : 'Refresh Prices'}
        </Button>
      </Box>
    </Paper>
  );
};

export default Watchlist;
