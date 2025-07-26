import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Paper,
  Button,
  useTheme,
  TextField,
  MenuItem,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab
} from '@mui/material';
import {
  PlayArrow as PlayArrowIcon,
  Assessment as AssessmentIcon,
  Timeline as TimelineIcon,
  SwapHoriz as SwapHorizIcon,
  Launch as LaunchIcon,
  Info as InfoIcon
} from '@mui/icons-material';
import Sidebar from '../common/Sidebar';
import { useAuth } from '../router/AuthContext';
import { useStrategy } from '../../context/StrategyContext';
import { getApiBaseUrl } from '../../utils/apiConfig';
import { backtestApi, strategyApi } from '../../api/Client';
import BacktestResults from './BacktestResults';

const Backtest = () => {
  const theme = useTheme();
  const { strategies, defaultStrategies, loading: strategiesLoading, refreshStrategies } = useStrategy();
  
  // Main state management
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [backtestListKey, setBacktestListKey] = useState(0);
  
  // Strategy and configuration state
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [backtestConfig, setBacktestConfig] = useState({
    initial_capital: 100000,
    timeframe: '1d',
    start_date: '2023-01-01',
    end_date: '2023-12-31',
    data_provider: 'alpaca'
  });
  
  // Results state
  const [deployDialog, setDeployDialog] = useState(false);
  const [deployType, setDeployType] = useState('paper');
  
  // Load default strategies with IDs for backtest selection
  useEffect(() => {
    const loadDefaultStrategiesWithIds = async () => {
      try {
        const strategies = await strategyApi.getDefaultStrategiesWithIds();
        console.log('Loaded default strategies with IDs:', strategies);
        setDefaultStrategiesWithIds(strategies); // Add this state variable
      } catch (error) {
        console.error('Error loading default strategies with IDs:', error);
      }
    };
    
    loadDefaultStrategiesWithIds();
  }, []);

  // Add the missing state variable
  const [defaultStrategiesWithIds, setDefaultStrategiesWithIds] = useState([]);
  
  // Load available strategies on component mount
  useEffect(() => {
    // Refresh strategies when component mounts
    refreshStrategies();
  }, [refreshStrategies]);
  
  // Combine user strategies and default strategies for dropdown
  const availableStrategies = useMemo(() => {
    const combinedStrategies = [];
    
    console.log('Raw strategies from context:', strategies);
    console.log('Raw defaultStrategiesWithIds:', defaultStrategiesWithIds);
    
    // Add user's custom strategies
    strategies.forEach(strategy => {
      const strategyId = String(strategy.id || strategy._id);
      console.log('Processing custom strategy:', strategy.name, 'ID:', strategyId);
      combinedStrategies.push({
        id: strategyId,
        name: strategy.name,
        description: strategy.description,
        type: 'custom',
        is_active: strategy.is_active
      });
    });
    
    // Add default strategies with their proper IDs
    defaultStrategiesWithIds.forEach(strategy => {
      console.log('Processing default strategy with ID:', strategy.name, 'ID:', strategy.id);
      combinedStrategies.push({
        id: strategy.id,
        name: strategy.name,
        description: strategy.description,
        type: 'default',
        is_active: true
      });
    });
    
    console.log('Final combined strategies for backtest:', combinedStrategies);
    return combinedStrategies;
  }, [strategies, defaultStrategiesWithIds]);
  
  const handleRunBacktest = async () => {
    if (!selectedStrategy) {
      setError('Please select a strategy');
      return;
    }
    
    try {
      setLoading(true);
      setError(null);
      
      console.log('Running backtest with strategy ID:', selectedStrategy);
      console.log('Available strategies:', availableStrategies);
      console.log('Default strategies with IDs:', defaultStrategiesWithIds); // This state is no longer needed
      console.log('Selected strategy type:', typeof selectedStrategy);
      console.log('Strategy ID for backtest request:', selectedStrategy);
      
      await backtestApi.runBacktest({
        strategy_id: selectedStrategy,
        ...backtestConfig
      });
      
      setBacktestListKey(prevKey => prevKey + 1);
    } catch (err) {
      console.error('Error running backtest:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  const handleDeployStrategy = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${getApiBaseUrl()}/api/backtest/deploy/${selectedStrategy}?deploy_type=${deployType}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to deploy strategy');
      }
      
      setDeployDialog(false);
      setError(null);
      // Show success message
      alert(`Strategy deployed to ${deployType} trading successfully!`);
    } catch (err) {
      console.error('Error deploying strategy:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  const handleBacktestSelect = (backtest) => {
    // You can implement logic here to load the full backtest details
    console.log('Selected backtest:', backtest);
    // Optionally set this as the current backtest result
    // setBacktestResult(backtest);
  };

  // Main configuration view
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom sx={{ color: theme.palette.text.primary, fontWeight: 'bold' }}>
        Strategy Backtest
      </Typography>
      
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}
      
      <Grid container spacing={3}>
        {/* Configuration Panel */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Backtest Configuration
            </Typography>
            
            <Grid container spacing={3}>
              {/* Strategy Selection */}
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  select
                  label="Select Strategy"
                  value={selectedStrategy}
                  onChange={(e) => {
                    const selectedValue = e.target.value;
                    console.log('Strategy selected - Raw value:', selectedValue, typeof selectedValue);
                    const foundStrategy = availableStrategies.find(s => s.id === selectedValue);
                    console.log('Found strategy object:', foundStrategy);
                    setSelectedStrategy(selectedValue);
                  }}
                  disabled={strategiesLoading}
                  helperText={strategiesLoading ? "Loading strategies..." : `${availableStrategies.length} strategies available`}
                  SelectProps={{
                    displayEmpty: true,
                    renderValue: (selected) => {
                      if (!selected) {
                        return <Typography color="textSecondary"></Typography>;
                      }
                      const strategy = availableStrategies.find(s => s.id === selected);
                      return strategy ? strategy.name : '';
                    }
                  }}
                >
                  <MenuItem value="">
                    <Typography color="textSecondary">Choose a strategy...</Typography>
                  </MenuItem>
                  {availableStrategies.map((strategy) => {
                    
                    return (
                      <MenuItem key={strategy.id} value={strategy.id}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography>{strategy.name}</Typography>
                          <Chip 
                            label={strategy.type} 
                            size="small" 
                            color={strategy.type === 'custom' ? 'primary' : 'secondary'}
                          />
                        </Box>
                      </MenuItem>
                    );
                  })}
                </TextField>
              </Grid>
              
              {/* Configuration Fields */}
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Initial Capital ($)"
                  type="number"
                  value={backtestConfig.initial_capital}
                  onChange={(e) => setBacktestConfig(prev => ({
                    ...prev,
                    initial_capital: parseFloat(e.target.value)
                  }))}
                  helperText=" "
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  select
                  label="Timeframe"
                  value={backtestConfig.timeframe}
                  onChange={(e) => setBacktestConfig(prev => ({
                    ...prev,
                    timeframe: e.target.value
                  }))}
                  helperText=" "
                >
                  <MenuItem value="1m">1 Minute</MenuItem>
                  <MenuItem value="5m">5 Minutes</MenuItem>
                  <MenuItem value="15m">15 Minutes</MenuItem>
                  <MenuItem value="1h">1 Hour</MenuItem>
                  <MenuItem value="1d">1 Day</MenuItem>
                  <MenuItem value="1w">1 Week</MenuItem>
                </TextField>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Start Date"
                  type="date"
                  value={backtestConfig.start_date}
                  onChange={(e) => setBacktestConfig(prev => ({
                    ...prev,
                    start_date: e.target.value
                  }))}
                  InputLabelProps={{ shrink: true }}
                  helperText=" "
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="End Date"
                  type="date"
                  value={backtestConfig.end_date}
                  onChange={(e) => setBacktestConfig(prev => ({
                    ...prev,
                    end_date: e.target.value
                  }))}
                  InputLabelProps={{ shrink: true }}
                  helperText=" "
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  select
                  label="Data Provider"
                  value={backtestConfig.data_provider}
                  onChange={(e) => setBacktestConfig(prev => ({
                    ...prev,
                    data_provider: e.target.value
                  }))}
                  helperText=" "
                >
                  <MenuItem value="alpaca">Alpaca</MenuItem>
                  <MenuItem value="polygon">Polygon</MenuItem>
                  <MenuItem value="yahoo">Yahoo Finance</MenuItem>
                </TextField>
              </Grid>
            </Grid>
            
            <Box sx={{ mt: 3, display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                startIcon={loading ? <CircularProgress size={20} /> : <PlayArrowIcon />}
                onClick={handleRunBacktest}
                disabled={loading || !selectedStrategy}
                sx={{ minWidth: 200 }}
              >
                {loading ? 'Running Backtest...' : 'Run Backtest'}
              </Button>
            </Box>
          </Paper>
        </Grid>
        
        {/* Previous Backtests */}
        <Grid item xs={12}>
          <BacktestResults 
            key={backtestListKey}
            strategies={availableStrategies}
            onBacktestSelect={handleBacktestSelect}
          />
        </Grid>
      </Grid>
    </Container>
  );
};

export default Backtest;
