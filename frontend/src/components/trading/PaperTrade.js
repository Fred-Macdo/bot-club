// src/components/trading/PaperTradingPage.js
import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  useTheme,
  Container,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Grid,
  Paper,
  Chip,
  Alert,
  CircularProgress,
  Autocomplete,
  TextField
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
  Assessment as AssessmentIcon
} from '@mui/icons-material';
import { DataGrid } from '@mui/x-data-grid';
import Plot from 'react-plotly.js';
import { useStrategy } from '../../context/StrategyContext';
import { fetchDefaultStrategies } from '../../api/Client';

const transformDefaultStrategies = (backendStrategies) => {
  return backendStrategies.map((strategy, index) => {
    const indicators = strategy.config?.indicators?.map(ind => ind.name) || [];
    
    // Determine category based on strategy name/indicators
    let category = 'Trading';
    if (strategy.name.toLowerCase().includes('ema') || strategy.name.toLowerCase().includes('crossover')) {
      category = 'Trend Following';
    } else if (strategy.name.toLowerCase().includes('bollinger')) {
      category = 'Breakout';
    } else if (strategy.name.toLowerCase().includes('macd')) {
      category = 'Momentum';
    } else if (strategy.name.toLowerCase().includes('rsi')) {
      category = 'Mean Reversion';
    }
    
    // Determine complexity based on number of indicators and conditions
    let complexity = 'Beginner';
    const totalConditions = (strategy.config?.entry_conditions?.length || 0) + 
                          (strategy.config?.exit_conditions?.length || 0);
    if (totalConditions > 3 || indicators.length > 2) {
      complexity = 'Advanced';
    } else if (totalConditions > 1 || indicators.length > 1) {
      complexity = 'Intermediate';
    }
    
    return {
      id: `default_${index + 1}`,
      name: strategy.name,
      description: strategy.description || 'No description provided',
      type: 'default',
      category,
      performance: 'N/A', // Will be populated after backtesting
      complexity,
      indicators,
      timeframes: strategy.config?.timeframe ? [strategy.config.timeframe.toUpperCase()] : ['1D'],
      backtestReturn: null,
      sharpeRatio: null,
      maxDrawdown: null,
      winRate: null,
      totalTrades: null,
      config: strategy.config // Store original config for potential use
    };
  });
};


const PaperTradingPage = () => {
  const theme = useTheme();
  const { strategies: userStrategies } = useStrategy();
  
  // State for strategy selection and deployment
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [dataProvider, setDataProvider] = useState('alpaca');
  const [defaultStrategies, setDefaultStrategies] = useState([]);
  const [isDeployed, setIsDeployed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [defaultStrategiesLoading, setDefaultStrategiesLoading] = useState(true);
  const [defaultStrategiesError, setDefaultStrategiesError] = useState(null);
  
  // State for trading data
  const [pnlData, setPnlData] = useState([]);
  const [trades, setTrades] = useState([]);
  const [logs, setLogs] = useState([]);
  const [currentPnL, setCurrentPnL] = useState(0);
  
  // Mock data for development
  useEffect(() => {
    const loadDefaultStrategies = async () => {
      try {
        setDefaultStrategiesLoading(true);
        setDefaultStrategiesError(null);
        const result = await fetchDefaultStrategies();
          if (result.success) {
          // Transform backend data to match frontend format
          const transformedStrategies = transformDefaultStrategies(result.strategies);
          setDefaultStrategies(transformedStrategies);
        } else {
          setDefaultStrategiesError(result.error);
        }
      } catch (error) {
        console.error('Error loading default strategies:', error);
        setDefaultStrategiesError('Failed to load default strategies');
      } finally {
        setDefaultStrategiesLoading(false);
      }
    };

    loadDefaultStrategies();

    // Mock initial logs
    setLogs([
      { timestamp: new Date(), level: 'INFO', message: 'Paper trading system initialized' },
      { timestamp: new Date(Date.now() - 60000), level: 'INFO', message: 'Market data connection established' }
    ]);
  }, []);

  // Combine default and user strategies
  const allStrategies = useMemo(() => {
    const userStrategiesFormatted = userStrategies.map(strategy => ({
      id: strategy.id,
      name: strategy.name,
      description: strategy.description || 'No description provided',
      type: 'user',
      category: 'Custom',
      performance: 'N/A',
      complexity: 'Custom',
      indicators: strategy.config?.indicators?.map(ind => ind.name) || [],
      timeframes: strategy.config?.timeframe ? [strategy.config.timeframe] : [],
      backtestReturn: null,
      sharpeRatio: null,
      maxDrawdown: null,
      winRate: null,
      totalTrades: null,
      createdAt: strategy.created_at
    }));

    return [...defaultStrategies, ...userStrategiesFormatted];
  }, [userStrategies, defaultStrategies]);

  // Mock real-time updates when deployed
  useEffect(() => {
    if (!isDeployed) return;
    
    const interval = setInterval(() => {
      const newPnL = currentPnL + (Math.random() - 0.5) * 100;
      setCurrentPnL(newPnL);
      setPnlData(prev => [...prev, { timestamp: new Date(), value: newPnL }].slice(-100));
      
      const logMessages = [
        'Checking entry conditions for GOOGL (Paper)',
        'Market data updated (Paper)',
        'Paper order executed',
        'Signal generated for AMZN (Paper)'
      ];
      
      if (Math.random() > 0.7) {
        setLogs(prev => [{
          timestamp: new Date(),
          level: Math.random() > 0.8 ? 'WARNING' : 'INFO',
          message: logMessages[Math.floor(Math.random() * logMessages.length)]
        }, ...prev].slice(0, 50));
      }
    }, 2000);
    
    return () => clearInterval(interval);
  }, [isDeployed, currentPnL]);

  const handleDeployStrategy = async () => {
    if (!selectedStrategy) {
      alert('Please select a strategy first');
      return;
    }
    
    setIsLoading(true);
    
    try {
      await new Promise(resolve => setTimeout(resolve, 1500));
      setIsDeployed(true);
      setLogs(prev => [{
        timestamp: new Date(),
        level: 'INFO',
        message: `Paper strategy deployed: ${selectedStrategy?.name}`
      }, ...prev]);
      
      // Reset data on new deployment
      setPnlData([{ timestamp: new Date(), value: 0 }]);
      setCurrentPnL(0);
      setTrades([]);
      
    } catch (error) {
      console.error('Deployment error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopStrategy = async () => {
    setIsLoading(true);
    
    try {
      await new Promise(resolve => setTimeout(resolve, 1500));
      setIsDeployed(false);
      setLogs(prev => [{
        timestamp: new Date(),
        level: 'INFO',
        message: `Paper strategy stopped: ${selectedStrategy?.name}`
      }, ...prev]);
    } catch (error) {
      console.error('Stopping error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const mockTrades = [
    { id: 1, symbol: 'GOOGL', side: 'BUY', quantity: 10, entryPrice: 140.50, exitPrice: null, entryTime: new Date(Date.now() - 3600000), exitTime: null, pnl: 45.10, status: 'OPEN' },
    { id: 2, symbol: 'AMZN', side: 'SELL', quantity: 20, entryPrice: 135.10, exitPrice: 138.00, entryTime: new Date(Date.now() - 7200000), exitTime: new Date(Date.now() - 1800000), pnl: -58.00, status: 'CLOSED' }
  ];

  const tradeColumns = [
    { field: 'id', headerName: 'ID', width: 70 },
    { field: 'symbol', headerName: 'Symbol', width: 100 },
    { field: 'side', headerName: 'Side', width: 80, renderCell: (params) => (<Chip label={params.value} color={params.value === 'BUY' ? 'success' : 'error'} size="small"/>) },
    { field: 'quantity', headerName: 'Quantity', width: 100, type: 'number' },
    { field: 'entryPrice', headerName: 'Entry Price', width: 120, type: 'number', valueFormatter: (params) => `$${params.value?.toFixed(2) || 'N/A'}` },
    { field: 'exitPrice', headerName: 'Exit Price', width: 120, type: 'number', valueFormatter: (params) => `$${params.value?.toFixed(2) || 'N/A'}` },
    { field: 'entryTime', headerName: 'Entry Time', width: 180, type: 'dateTime', valueFormatter: (params) => params.value?.toLocaleString() || 'N/A' },
    { field: 'exitTime', headerName: 'Exit Time', width: 180, type: 'dateTime', valueFormatter: (params) => params.value?.toLocaleString() || 'N/A' },
    { field: 'pnl', headerName: 'P&L', width: 120, type: 'number', renderCell: (params) => (<Typography variant="body2" sx={{ color: params.value >= 0 ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>${params.value?.toFixed(2) || '0.00'}</Typography>) },
    { field: 'status', headerName: 'Status', width: 100, renderCell: (params) => (<Chip label={params.value} color={params.value === 'OPEN' ? 'warning' : 'default'} size="small"/>) }
  ];

  const pnlPlotData = [{ x: pnlData.map(d => d.timestamp), y: pnlData.map(d => d.value), type: 'scatter', mode: 'lines', name: 'P&L', line: { color: currentPnL >= 0 ? theme.palette.success.main : theme.palette.error.main, width: 2 } }];
  const pnlPlotLayout = { title: 'Paper Trading P&L', xaxis: { title: 'Time' }, yaxis: { title: 'P&L ($)', tickformat: '$,.0f' }, plot_bgcolor: theme.palette.background.paper, paper_bgcolor: theme.palette.background.paper, font: { color: theme.palette.text.primary }, margin: { l: 60, r: 30, b: 50, t: 50 } };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom sx={{ color: theme.palette.primary.main, fontWeight: 700, mb: 3 }}>
        <AssessmentIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
        Paper Trading
      </Typography>

      <Accordion defaultExpanded sx={{ mb: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
            <Typography variant="h6">Strategy Deployment</Typography>
            {isDeployed && <Chip label="ACTIVE" color="success" size="small" sx={{ ml: 'auto', mr: 2 }} />}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
            <Box sx={{ flex: '1 1 300px', minWidth: '250px' }}>
              <Autocomplete
                options={allStrategies}
                getOptionLabel={(option) => option.name}
                value={selectedStrategy}
                onChange={(event, newValue) => {
                  setSelectedStrategy(newValue);
                }}
                disabled={isDeployed}
                renderInput={(params) => <TextField {...params} label="Select Strategy" />}
              />
            </Box>
            <Box sx={{ flex: '1 1 150px', minWidth: '120px' }}>
              <FormControl fullWidth>
                <InputLabel>Data Provider</InputLabel>
                <Select value={dataProvider} onChange={(e) => setDataProvider(e.target.value)} label="Data Provider" disabled={isDeployed}>
                  <MenuItem value="alpaca">Alpaca</MenuItem>
                  <MenuItem value="polygon">Polygon</MenuItem>
                </Select>
              </FormControl>
            </Box>
            <Box sx={{ flex: '1 1 320px', minWidth: '320px', display: 'flex', gap: 2 }}>
                <Button
                    variant="contained"
                    fullWidth
                    startIcon={<PlayArrowIcon />}
                    onClick={handleDeployStrategy}
                    disabled={isLoading || isDeployed || !selectedStrategy}
                    color="primary"
                    sx={{ height: 56 }}
                >
                    Deploy Strategy
                </Button>
                <Button
                    variant="contained"
                    fullWidth
                    startIcon={<StopIcon />}
                    onClick={handleStopStrategy}
                    disabled={isLoading || !isDeployed}
                    color="error"
                    sx={{ height: 56 }}
                >
                    Stop Strategy
                </Button>
            </Box>
            {isDeployed && (
              <Box sx={{ width: '100%', mt: 2 }}>
                <Alert severity="info">Current P&L: <strong>${currentPnL.toFixed(2)}</strong></Alert>
              </Box>
            )}
          </Box>
        </AccordionDetails>
      </Accordion>

      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 2, height: 400 }}>
            <Typography variant="h6" gutterBottom>Strategy Performance</Typography>
            {isDeployed && pnlData.length > 1 ? (<Plot data={pnlPlotData} layout={pnlPlotLayout} style={{ width: '100%', height: '320px' }} config={{ responsive: true, displaylogo: false }}/>) : (<Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '320px', color: theme.palette.text.secondary }}>Deploy a strategy to see paper trading performance</Box>)}
          </Paper>
        </Grid>
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 2, height: 400, display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h6" gutterBottom>Trading Logs</Typography>
            <Box sx={{ flexGrow: 1, overflow: 'auto', border: `1px solid ${theme.palette.divider}`, borderRadius: 1, p: 1, backgroundColor: theme.palette.background.default }}>
              {logs.map((log, index) => (
                <Box key={index} sx={{ mb: 0.5, fontSize: '0.875rem', fontFamily: 'monospace' }}>
                  <Typography component="span" variant="body2" sx={{ color: theme.palette.text.secondary }}>{log.timestamp.toLocaleTimeString()}</Typography>
                  <Typography component="span" variant="body2" sx={{ color: log.level === 'WARNING' ? theme.palette.warning.main : theme.palette.info.main, mx: 1 }}>[{log.level}]</Typography>
                  <Typography component="span" variant="body2">{log.message}</Typography>
                </Box>
              ))}
            </Box>
          </Paper>
        </Grid>
      </Grid>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>Trade History</Typography>
        <Box sx={{ height: 400, width: '100%' }}>
          <DataGrid rows={isDeployed ? mockTrades : []} columns={tradeColumns} pageSize={5} rowsPerPageOptions={[5]} disableSelectionOnClick sx={{ '& .MuiDataGrid-cell': { borderColor: theme.palette.divider }, '& .MuiDataGrid-columnHeaders': { backgroundColor: theme.palette.background.default, borderColor: theme.palette.divider } }} />
        </Box>
      </Paper>
    </Container>
  );
};

export default PaperTradingPage;