import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  useTheme,
  Switch,
  FormControlLabel,
  Alert,
  CircularProgress,
} from '@mui/material';
import { useAlpaca } from '../../context/AlpacaContext';
import GettingStarted from '../docs/GettingStarted';
import Watchlist from './Watchlist';

// Import all the new subcomponents
import AccountPerformanceChart from './subcomponents/AccountPerformanceChart';
import PerformanceAnalytics from './subcomponents/PerformanceAnalytics';
import DashboardStatsCards from './subcomponents/DashboardStatsCards';
import DeployedStrategies from './subcomponents/DeployedStrategies';
import PortfolioSnapshot from './subcomponents/PortfolioSnapshot';
import KeyRiskMetrics from './subcomponents/KeyRiskMetrics';
import RecentActivityTable from './subcomponents/RecentActivityTable';

const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes in milliseconds
const CACHE_KEY_PREFIX = 'dashboard_cache_';

const EquityCurveDashboard = () => {
  const theme = useTheme();

  // Get config from the new context
  const { 
    paperConfig, 
    liveConfig, 
    isAlpacaConfigured, 
    loading: configLoading, 
    error: configError 
  } = useAlpaca();
  
  const [isPaperMode, setIsPaperMode] = useState(false);

  // State for data
  const [accountEquityData, setAccountEquityData] = useState([]);
  const [accountPlotData, setAccountPlotData] = useState([]);
  const [accountPlotLayout, setAccountPlotLayout] = useState({});
  const [dashboardStats, setDashboardStats] = useState(null);
  const [dashboardTrades, setDashboardTrades] = useState([]);

  // State for UI feedback during data fetching
  const [dataLoading, setDataLoading] = useState(true);
  const [dataError, setDataError] = useState(null);
  const [isUsingCache, setIsUsingCache] = useState(false);

  // Sorting states
  const [orderBy, setOrderBy] = useState('entryDate');
  const [order, setOrder] = useState('desc');

  // Cache helper functions
  const getCacheKey = (mode) => `${CACHE_KEY_PREFIX}${mode}`;

  const getCachedData = (mode) => {
    try {
      const cacheKey = getCacheKey(mode);
      const cached = localStorage.getItem(cacheKey);
      if (!cached) return null;

      const { data, timestamp } = JSON.parse(cached);
      const now = Date.now();
      
      // Check if cache is still valid
      if (now - timestamp < CACHE_DURATION) {
        return data;
      }
      
      // Remove expired cache
      localStorage.removeItem(cacheKey);
      return null;
    } catch (error) {
      console.error('Error reading cache:', error);
      return null;
    }
  };

  const setCachedData = (mode, data) => {
    try {
      const cacheKey = getCacheKey(mode);
      const cacheEntry = {
        data,
        timestamp: Date.now()
      };
      localStorage.setItem(cacheKey, JSON.stringify(cacheEntry));
    } catch (error) {
      console.error('Error setting cache:', error);
      // If localStorage is full or unavailable, continue without caching
    }
  };

  const clearCache = () => {
    localStorage.removeItem(getCacheKey('paper'));
    localStorage.removeItem(getCacheKey('live'));
  };

  // Add sorting functions
  const handleRequestSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
  };

  // Set initial paper/live mode once config is loaded
  useEffect(() => {
    if (!configLoading && isAlpacaConfigured) {
      // Default to live if available, otherwise paper
      setIsPaperMode(!liveConfig);
    }
  }, [configLoading, isAlpacaConfigured, liveConfig]);

  // Fetch data from Alpaca when mode or config changes
  useEffect(() => {
    if (configLoading || !isAlpacaConfigured) return;

    const fetchAlpacaData = async () => {
      setDataLoading(true);
      setDataError(null);
      setIsUsingCache(false);

      const config = isPaperMode ? paperConfig : liveConfig;
      const mode = isPaperMode ? 'paper' : 'live';

      if (!config) {
        setDataError(`The selected account (${isPaperMode ? 'Paper' : 'Live'}) is not configured.`);
        setDataLoading(false);
        return;
      }

      // Check for cached data first
      const cachedData = getCachedData(mode);
      if (cachedData) {
        console.log('Using cached dashboard data');
        setIsUsingCache(true);
        processAlpacaData(cachedData);
        setDataLoading(false);
        
        // Optionally, fetch fresh data in the background
        fetchFreshData(config, mode, true);
        return;
      }

      // No cache, fetch fresh data
      await fetchFreshData(config, mode, false);
    };

    const fetchFreshData = async (config, mode, isBackgroundUpdate = false) => {
      const headers = {
        'APCA-API-KEY-ID': config.key,
        'APCA-API-SECRET-KEY': config.secret,
      };

      try {
        const [account, portfolioHistory, activities] = await Promise.all([
          fetch(`${config.endpoint}/account`, { headers }).then(res => res.json()),
          fetch(`${config.endpoint}/account/portfolio/history`, { headers }).then(res => res.json()),
          fetch(`${config.endpoint}/account/activities`, { headers }).then(res => res.json())
        ]);
        
        if (account.code || portfolioHistory.code || (Array.isArray(activities) && activities.code)) {
            throw new Error(account.message || portfolioHistory.message || activities.message || 'Invalid API key or secret.');
        }

        const freshData = { account, portfolioHistory, activities };
        
        // Cache the fresh data
        setCachedData(mode, freshData);
        
        // Process and display the data
        processAlpacaData(freshData);
        
        if (isBackgroundUpdate) {
          console.log('Dashboard data refreshed in background');
        }
      } catch (err) {
        if (!isBackgroundUpdate) {
          setDataError(`Failed to load data from Alpaca: ${err.message}`);
        } else {
          console.error('Background refresh failed:', err);
        }
      } finally {
        if (!isBackgroundUpdate) {
          setDataLoading(false);
        }
      }
    };

    const processAlpacaData = ({ account, portfolioHistory, activities }) => {
      if (portfolioHistory && portfolioHistory.timestamp) {
        const equityData = portfolioHistory.timestamp.map((ts, index) => ({
          date: new Date(ts * 1000),
          value: portfolioHistory.equity[index],
        }));
        setAccountEquityData(equityData);
        
        const initialCapital = portfolioHistory.equity[0];
        const finalEquity = parseFloat(account.equity);
        const totalReturn = ((finalEquity - initialCapital) / initialCapital) * 100;
        
        let peak = initialCapital;
        let maxDrawdown = 0;
        portfolioHistory.equity.forEach(value => {
          if (value > peak) peak = value;
          const drawdown = ((peak - value) / peak) * 100;
          if (drawdown > maxDrawdown) maxDrawdown = drawdown;
        });

        const tradeActivities = activities.filter(a => a.activity_type === 'FILL');
        const winningTrades = tradeActivities.filter(t => parseFloat(t.net_amount) > 0).length;

        setDashboardStats({
          initialCapital,
          finalEquity,
          totalReturn,
          totalTrades: tradeActivities.length,
          winningTrades,
          losingTrades: tradeActivities.length - winningTrades,
          winRate: tradeActivities.length > 0 ? (winningTrades / tradeActivities.length) * 100 : 0,
          maxDrawdown: maxDrawdown,
          sharpeRatio: 'N/A',
          profitFactor: 'N/A',
        });
      }
      
      if (Array.isArray(activities)) {
          const trades = activities.filter(a => a.activity_type === 'FILL').map(trade => ({
            id: trade.id,
            symbol: trade.symbol,
            side: trade.side,
            entryDate: new Date(trade.transaction_time),
            entryPrice: parseFloat(trade.price),
            shares: parseFloat(trade.qty),
            pnl: parseFloat(trade.net_amount)
          }));
          setDashboardTrades(trades);
      }
    };

    fetchAlpacaData();
  }, [isPaperMode, isAlpacaConfigured, paperConfig, liveConfig, configLoading]);
  
  // Update plot when data changes
  useEffect(() => {
    if (accountEquityData.length > 0) {
      const equityTrace = {
        x: accountEquityData.map(d => d.date),
        y: accountEquityData.map(d => d.value),
        type: 'scatter',
        mode: 'lines',
        name: 'Account Equity',
        line: { color: theme.palette.primary.main, width: 2 }
      };

      // Calculate dynamic Y-axis range based on data
      const values = accountEquityData.map(d => d.value);
      const minValue = Math.min(...values);
      const maxValue = Math.max(...values);
      const padding = (maxValue - minValue) * 0.1; // 10% padding
      
      setAccountPlotData([equityTrace]);
      setAccountPlotLayout({
        autosize: true,
        margin: { l: 70, r: 30, b: 50, t: 50, pad: 4 },
        xaxis: {
          title: 'Date',
          gridcolor: theme.palette.divider,
          linecolor: theme.palette.text.primary,
          tickfont: { color: theme.palette.text.secondary }
        },
        yaxis: {
          title: 'Portfolio Value ($)',
          gridcolor: theme.palette.divider,
          linecolor: theme.palette.text.secondary,
          tickfont: { color: theme.palette.text.secondary },
          tickformat: '$,.0f',
          range: [minValue - padding, maxValue + padding], // Dynamic range
          autorange: false // Disable autorange to use our custom range
        },
        legend: {
          orientation: 'h',
          yanchor: 'bottom',
          y: 1.02,
          xanchor: 'right',
          x: 1,
          font: { color: theme.palette.text.secondary }
        },
        plot_bgcolor: theme.palette.background.paper,
        paper_bgcolor: theme.palette.background.paper,
        font: { color: theme.palette.text.primary },
        hovermode: 'closest',
        // Force plot to re-render completely when switching accounts
        revision: `${isPaperMode ? 'paper' : 'live'}_${Date.now()}`
      });
    }
  }, [accountEquityData, theme.palette, isPaperMode]); // Add isPaperMode as dependency

  // Clear plot data when switching modes to prevent layout issues
  useEffect(() => {
    setAccountPlotData([]);
    setAccountPlotLayout({});
    setAccountEquityData([]);
  }, [isPaperMode]);

  // Handle various loading and error states
  if (configLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4, textAlign: 'center' }}>
        <CircularProgress />
        <Typography>Loading Configuration...</Typography>
      </Container>
    );
  }

  if (!isAlpacaConfigured) {
    return <GettingStarted />;
  }
  
  if (configError || dataError) {
    return (
      <Container maxWidth="lg" sx={{ py: 4, textAlign: 'center' }}>
        <Alert severity="error">{configError || dataError}</Alert>
      </Container>
    );
  }
  
  if (dataLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4, textAlign: 'center' }}>
        <CircularProgress />
        <Typography>Loading Dashboard Data from Alpaca...</Typography>
      </Container>
    );
  }

  return (
    <Container maxWidth={'xl'} sx={{ py: 4, px: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
          Account Dashboard
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <FormControlLabel
            control={
              <Switch 
                checked={isPaperMode} 
                onChange={() => setIsPaperMode(!isPaperMode)} 
                disabled={dataLoading || (isPaperMode && !paperConfig) || (!isPaperMode && !liveConfig)}
              />
            }
            label={isPaperMode ? "Paper Account" : "Live Account"}
          />
        </Box>
      </Box>
      
      <Grid container spacing={3}>
        {/* Left Column - Performance Chart and Analytics */}
        <Grid item xs={12} lg={8}>
          <AccountPerformanceChart 
            plotData={accountPlotData} 
            plotLayout={accountPlotLayout} 
          />
          <PerformanceAnalytics stats={dashboardStats} />
        </Grid>

        {/* Right Column - Stats and Controls */}
        <Grid item xs={12} lg={4}>
          <DashboardStatsCards stats={dashboardStats} />
          <DeployedStrategies isPaperMode={isPaperMode} />
          <PortfolioSnapshot stats={dashboardStats} />
          <KeyRiskMetrics stats={dashboardStats} />
        </Grid>

        {/* Bottom Row - Recent Activity and Watchlist */}
        <Grid item xs={12}>
          <Grid container spacing={3}>
            <Grid item xs={12} lg={6}>
              <RecentActivityTable 
                trades={dashboardTrades}
                orderBy={orderBy}
                order={order}
                handleRequestSort={handleRequestSort}
              />
            </Grid>

            {/* Watchlist in bottom right */}
            <Grid item xs={12} lg={6}>
              <Watchlist />
            </Grid>
          </Grid>
        </Grid>
      </Grid>
    </Container>
  );
};

export default EquityCurveDashboard;