import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  InputAdornment,
  Chip,
  IconButton,
  Button,
  Grid,
  useTheme,
  CircularProgress,
  Tab,
  Tabs
} from '@mui/material';
import {
  Search as SearchIcon,
  FilterList as FilterListIcon,
  PlayArrow as PlayArrowIcon,
  Favorite as FavoriteIcon,
  FavoriteBorder as FavoriteBorderIcon,
  Info as InfoIcon
} from '@mui/icons-material';
import Sidebar from '../common/Sidebar';
import { useStrategy } from '../../context/StrategyContext';
import { useAuth } from '../router/AuthContext';
import { fetchDefaultStrategies } from '../../api/Client';

// Transform backend strategy data to frontend format
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

const StrategyLibrary = () => {
  const theme = useTheme();
  const { user } = useAuth();
  const { strategies: userStrategies, loading: strategiesLoading } = useStrategy();
  
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState(0); // 0: All, 1: Default, 2: User
  const [favorites, setFavorites] = useState(new Set());
  const [defaultStrategies, setDefaultStrategies] = useState([]);
  const [defaultStrategiesLoading, setDefaultStrategiesLoading] = useState(true);
  const [defaultStrategiesError, setDefaultStrategiesError] = useState(null);
  // Fetch default strategies on component mount
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
  }, []);

  // Combine default and user strategies
  const allStrategies = useMemo(() => {
    const userStrategiesFormatted = userStrategies.map(strategy => ({
      id: strategy.id || strategy._id,
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
  }, [userStrategies]);

  // Filter strategies based on search term and active tab
  const filteredStrategies = useMemo(() => {
    let filtered = allStrategies;

    // Filter by tab
    if (activeTab === 1) {
      filtered = filtered.filter(strategy => strategy.type === 'default');
    } else if (activeTab === 2) {
      filtered = filtered.filter(strategy => strategy.type === 'user');
    }

    // Filter by search term
    if (searchTerm) {
      filtered = filtered.filter(strategy =>
        strategy.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        strategy.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
        strategy.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
        strategy.indicators.some(indicator => 
          indicator.toLowerCase().includes(searchTerm.toLowerCase())
        )
      );
    }

    return filtered;
  }, [allStrategies, searchTerm, activeTab]);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const toggleFavorite = (strategyId) => {
    const newFavorites = new Set(favorites);
    if (newFavorites.has(strategyId)) {
      newFavorites.delete(strategyId);
    } else {
      newFavorites.add(strategyId);
    }
    setFavorites(newFavorites);
  };

  const getComplexityColor = (complexity) => {
    switch (complexity) {
      case 'Beginner':
        return theme.palette.success.main;
      case 'Intermediate':
        return theme.palette.warning.main;
      case 'Advanced':
        return theme.palette.error.main;
      default:
        return theme.palette.primary.main;
    }
  };

  const getPerformanceColor = (performance) => {
    if (performance === 'N/A') return theme.palette.text.secondary;
    const value = parseFloat(performance.replace('%', ''));
    return value >= 0 ? theme.palette.success.main : theme.palette.error.main;
  };
  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" sx={{ fontWeight: 'bold', mb: 1 }}>
          Strategy Library
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Browse and discover trading strategies from our curated library and community
        </Typography>
      </Box>

        {/* Search and Filter Controls */}
        <Paper sx={{ p: 2, mb: 3, borderRadius: 2 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={8}>
              <TextField
                fullWidth
                placeholder="Search strategies by name, description, or indicators..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon color="action" />
                    </InputAdornment>
                  ),
                }}
                size="small"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <Tabs
                value={activeTab}
                onChange={handleTabChange}
                variant="fullWidth"
                sx={{
                  '& .MuiTab-root': {
                    textTransform: 'none',
                    minHeight: 36,
                    fontSize: '0.875rem'
                  }
                }}
              >
                <Tab label={`All (${allStrategies.length})`} />
                <Tab label={`Default (${defaultStrategies.length})`} />
                <Tab label={`My Strategies (${userStrategies.length})`} />
              </Tabs>
            </Grid>
          </Grid>
        </Paper>

        {/* Strategies Table */}
        <Paper sx={{ borderRadius: 2 }}>
          <TableContainer sx={{ maxHeight: 600 }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>Strategy</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Category</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Indicators</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Performance</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Complexity</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Win Rate</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Actions</TableCell>
                </TableRow>
              </TableHead>              <TableBody>
                {(strategiesLoading || defaultStrategiesLoading) ? (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                      <CircularProgress size={24} />
                      <Typography variant="body2" sx={{ mt: 1 }}>
                        Loading strategies...
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : defaultStrategiesError ? (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                      <Typography variant="body2" color="error">
                        Error loading default strategies: {defaultStrategiesError}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : filteredStrategies.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                      <Typography variant="body2" color="text.secondary">
                        No strategies found matching your search criteria
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredStrategies.map((strategy, index) => (
                    <TableRow
                      key={strategy.id}
                      sx={{
                        '&:nth-of-type(odd)': {
                          backgroundColor: theme.palette.action.hover,
                        },
                        '&:hover': {
                          backgroundColor: theme.palette.action.selected,
                        },
                      }}
                    >
                      <TableCell>
                        <Box>
                          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                              {strategy.name}
                            </Typography>
                            {strategy.type === 'user' && (
                              <Chip
                                label="Custom"
                                size="small"
                                sx={{
                                  ml: 1,
                                  bgcolor: theme.palette.primary.main,
                                  color: 'white',
                                  fontSize: '0.65rem',
                                  height: 18
                                }}
                              />
                            )}
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
                            {strategy.description}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={strategy.category}
                          size="small"
                          variant="outlined"
                          sx={{ fontSize: '0.75rem' }}
                        />
                      </TableCell>
                      <TableCell>
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                          {strategy.indicators.slice(0, 3).map((indicator, idx) => (
                            <Chip
                              key={idx}
                              label={indicator}
                              size="small"
                              sx={{
                                bgcolor: 'rgba(13, 55, 42, 0.1)',
                                color: theme.palette.primary.main,
                                fontSize: '0.65rem',
                                height: 20
                              }}
                            />
                          ))}
                          {strategy.indicators.length > 3 && (
                            <Chip
                              label={`+${strategy.indicators.length - 3}`}
                              size="small"
                              sx={{
                                bgcolor: theme.palette.action.hover,
                                fontSize: '0.65rem',
                                height: 20
                              }}
                            />
                          )}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          sx={{
                            fontWeight: 'bold',
                            color: getPerformanceColor(strategy.performance)
                          }}
                        >
                          {strategy.performance}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography
                          variant="body2"
                          sx={{
                            fontWeight: 'bold',
                            color: getComplexityColor(strategy.complexity)
                          }}
                        >
                          {strategy.complexity}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {strategy.winRate ? `${strategy.winRate.toFixed(1)}%` : 'N/A'}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <IconButton
                            size="small"
                            onClick={() => toggleFavorite(strategy.id)}
                            sx={{ color: favorites.has(strategy.id) ? theme.palette.error.main : 'inherit' }}
                          >
                            {favorites.has(strategy.id) ? (
                              <FavoriteIcon fontSize="small" />
                            ) : (
                              <FavoriteBorderIcon fontSize="small" />
                            )}
                          </IconButton>
                          <IconButton
                            size="small"
                            sx={{ color: theme.palette.primary.main }}
                          >
                            <InfoIcon fontSize="small" />
                          </IconButton>
                          <IconButton
                            size="small"
                            sx={{ color: theme.palette.success.main }}
                          >
                            <PlayArrowIcon fontSize="small" />
                          </IconButton>
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>            </Table>
          </TableContainer>
        </Paper>

      {/* Library Statistics */}
      {!strategiesLoading && filteredStrategies.length > 0 && (
        <Paper sx={{ p: 2, mt: 3, borderRadius: 2 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
            Library Statistics
          </Typography>
          <Grid container spacing={3}>
            <Grid item xs={6} sm={3}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold', color: theme.palette.primary.main }}>
                  {filteredStrategies.length}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Total Strategies
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
                  {defaultStrategies.length}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Default Strategies
                </Typography>
              </Box>
            </Grid>              <Grid item xs={6} sm={3}>
                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="h4" sx={{ fontWeight: 'bold', color: theme.palette.info.main }}>
                    {userStrategies.length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Your Strategies
                  </Typography>
                </Box>
              </Grid>
            <Grid item xs={6} sm={3}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h4" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>
                  {favorites.size}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Favorites
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}
    </Box>
  );
};

export default StrategyLibrary;
