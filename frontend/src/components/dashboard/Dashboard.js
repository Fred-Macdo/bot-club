import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Paper,
  useTheme,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Card,
  CardContent,
  Switch,
  FormControlLabel,
  Alert,
  CircularProgress,
  Button,
  TableSortLabel,
} from '@mui/material';
import {
  MonetizationOn as MonetizationOnIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Assessment as AssessmentIcon,
} from '@mui/icons-material';
import Plot from 'react-plotly.js';
import { useAlpaca } from '../../context/AlpacaContext';
import { Link } from 'react-router-dom';
import GettingStarted from '../docs/GettingStarted';
import Watchlist from './Watchlist';


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

  // Sorting states
  const [orderBy, setOrderBy] = useState('entryDate');
  const [order, setOrder] = useState('desc');

  // Add sorting functions
  const handleRequestSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
  };

  const descendingComparator = (a, b, orderBy) => {
    if (b[orderBy] < a[orderBy]) {
      return -1;
    }
    if (b[orderBy] > a[orderBy]) {
      return 1;
    }
    return 0;
  };

  const getComparator = (order, orderBy) => {
    return order === 'desc'
      ? (a, b) => descendingComparator(a, b, orderBy)
      : (a, b) => -descendingComparator(a, b, orderBy);
  };

  const sortedTrades = dashboardTrades.slice().sort(getComparator(order, orderBy));

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

      const config = isPaperMode ? paperConfig : liveConfig;

      if (!config) {
        setDataError(`The selected account (${isPaperMode ? 'Paper' : 'Live'}) is not configured.`);
        setDataLoading(false);
        return;
      }

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

      } catch (err) {
        setDataError(`Failed to load data from Alpaca: ${err.message}`);
      } finally {
        setDataLoading(false);
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
          tickformat: '$,.0f'
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
        hovermode: 'closest'
      });
    }
  }, [accountEquityData, theme.palette]);

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
    <Container maxWidth={false} sx={{ py: 4, px: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
          Account Dashboard
        </Typography>
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
      <Grid container spacing={3}>
        {/* Left Column - Performance Chart */}
        <Grid item xs={12} lg={8}>
          <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Account Performance
            </Typography>
            <Box sx={{ width: '100%', height: 400 }}>
              <Plot
                data={accountPlotData}
                layout={accountPlotLayout}
                style={{ width: '100%', height: '100%' }}
                useResizeHandler={true}
                config={{ responsive: true, displaylogo: false }}
              />
            </Box>
          </Paper>

          <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Performance Analytics
            </Typography>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Overall Trade Statistics
              </Typography>
              <Grid container spacing={1}>
                <Grid item xs={6} sm={4}><Typography variant="body2">Total Trades:</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{dashboardStats?.totalTrades}</Typography></Grid>
                <Grid item xs={6} sm={4}><Typography variant="body2">Winning Trades:</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>{dashboardStats?.winningTrades} ({dashboardStats?.winRate?.toFixed(1)}%)</Typography></Grid>
                <Grid item xs={6} sm={4}><Typography variant="body2">Losing Trades:</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>{dashboardStats?.losingTrades} ({(100 - (dashboardStats?.winRate || 0))?.toFixed(1)}%)</Typography></Grid>
                <Grid item xs={6} sm={4}><Typography variant="body2">Avg. Win (%):</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>N/A</Typography></Grid>
                <Grid item xs={6} sm={4}><Typography variant="body2">Avg. Loss (%):</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>N/A</Typography></Grid>
              </Grid>
            </Box>
          </Paper>
        </Grid>

        {/* Right Column - Stats and Controls */}
        <Grid item xs={12} lg={4}>
          {/* Performance Stats Cards */}
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={6} lg={12}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <MonetizationOnIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
                    <Typography variant="subtitle2">Total Return</Typography>
                  </Box>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: dashboardStats?.totalReturn >= 0 ? theme.palette.success.main : theme.palette.error.main }}>
                    {dashboardStats?.totalReturn >= 0 ? '+' : ''}{dashboardStats?.totalReturn?.toFixed(2)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    ${dashboardStats?.initialCapital?.toFixed(2)} → ${dashboardStats?.finalEquity?.toFixed(2)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} lg={12}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <TrendingUpIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
                    <Typography variant="subtitle2">Win Rate</Typography>
                  </Box>
                  <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
                    {dashboardStats?.winRate?.toFixed(2)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {dashboardStats?.winningTrades} / {dashboardStats?.totalTrades} trades
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} lg={12}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <TrendingDownIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
                    <Typography variant="subtitle2">Max Drawdown</Typography>
                  </Box>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>
                    -{dashboardStats?.maxDrawdown?.toFixed(2)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Profit Factor: {dashboardStats?.profitFactor}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} lg={12}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <AssessmentIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
                    <Typography variant="subtitle2">Sharpe Ratio</Typography>
                  </Box>
                  <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
                    {dashboardStats?.sharpeRatio}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Avg Win: N/A | Avg Loss: N/A
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Account Overview */}
          <Paper sx={{ p: 2, borderRadius: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Box>
              <Typography variant="h6">
                Account Overview
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {isPaperMode ? "Paper Trading Performance" : "Live Trading Performance"}
              </Typography>
            </Box>
          </Paper>

          {/* Portfolio Snapshot */}
          <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>
              Portfolio Snapshot
            </Typography>
            <Box sx={{
              p: 2, borderRadius: 1,
              bgcolor: dashboardStats?.totalReturn >= 0 ? 'rgba(46, 125, 50, 0.1)' : 'rgba(211, 47, 47, 0.1)',
              border: 1, borderColor: dashboardStats?.totalReturn >= 0 ? 'rgba(46, 125, 50, 0.3)' : 'rgba(211, 47, 47, 0.3)'
            }}>
              <Typography variant="body2" sx={{ mb: 1 }}><strong>Initial Portfolio Value (approx.):</strong> ${dashboardStats?.initialCapital?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}><strong>Current Portfolio Value:</strong> ${dashboardStats?.finalEquity?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}><strong>Absolute Gain/Loss:</strong> ${(dashboardStats?.finalEquity - dashboardStats?.initialCapital)?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
              <Typography variant="body2" sx={{ fontWeight: 'bold' }}><strong>Total Return:</strong> {dashboardStats?.totalReturn >= 0 ? '+' : ''}{dashboardStats?.totalReturn?.toFixed(2)}%</Typography>
            </Box>
          </Paper>

          {/* Key Risk Metrics */}
          <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
              Key Risk Metrics
            </Typography>
            <Grid container spacing={1}>
              <Grid item xs={6}><Typography variant="body2">Max Drawdown:</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>{dashboardStats?.maxDrawdown?.toFixed(2)}%</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2">Sharpe Ratio:</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{dashboardStats?.sharpeRatio}</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2">Profit Factor:</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{dashboardStats?.profitFactor}</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2">Win Rate:</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{dashboardStats?.winRate?.toFixed(1)}%</Typography></Grid>
            </Grid>
          </Paper>
        </Grid>

        {/* Bottom Row - Recent Activity and Watchlist */}
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 3, borderRadius: 2, height: '500px', display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h6" gutterBottom>
              Recent Account Activity
            </Typography>
            <TableContainer sx={{ flexGrow: 1, maxHeight: 'none' }}>
              <Table stickyHeader size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'symbol'}
                        direction={orderBy === 'symbol' ? order : 'asc'}
                        onClick={() => handleRequestSort('symbol')}
                      >
                        Symbol
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'side'}
                        direction={orderBy === 'side' ? order : 'asc'}
                        onClick={() => handleRequestSort('side')}
                      >
                        Side
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'entryDate'}
                        direction={orderBy === 'entryDate' ? order : 'asc'}
                        onClick={() => handleRequestSort('entryDate')}
                      >
                        Date
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'entryPrice'}
                        direction={orderBy === 'entryPrice' ? order : 'asc'}
                        onClick={() => handleRequestSort('entryPrice')}
                      >
                        Price
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'shares'}
                        direction={orderBy === 'shares' ? order : 'asc'}
                        onClick={() => handleRequestSort('shares')}
                      >
                        Shares
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={orderBy === 'pnl'}
                        direction={orderBy === 'pnl' ? order : 'asc'}
                        onClick={() => handleRequestSort('pnl')}
                      >
                        Net P&L ($)
                      </TableSortLabel>
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sortedTrades.slice(0, 50).map((trade) => (
                    <TableRow
                      key={trade.id}
                      sx={{
                        '&:nth-of-type(odd)': { bgcolor: theme.palette.action.hover },
                        bgcolor: trade.pnl > 0 ? 'rgba(46, 125, 50, 0.04)' : 'rgba(211, 47, 47, 0.04)'
                      }}
                    >
                      <TableCell>
                        <Chip label={trade.symbol} size="small" sx={{ bgcolor: theme.palette.primary.light, color: theme.palette.primary.contrastText, fontSize: '0.75rem', height: 20 }} />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ color: trade.side === 'buy' ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>
                          {trade.side.toUpperCase()}
                        </Typography>
                      </TableCell>
                      <TableCell>{trade.entryDate.toLocaleDateString()}</TableCell>
                      <TableCell>${trade.entryPrice.toFixed(2)}</TableCell>
                      <TableCell>{trade.shares}</TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ color: trade.pnl > 0 ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>
                          {trade.pnl > 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Watchlist in bottom right */}
        <Grid item xs={12} lg={6}>
          <Watchlist />
        </Grid>
      </Grid>
    </Container>
  );
};

export default EquityCurveDashboard;