// src/components/trading/LiveTradingPage.js
import React from 'react';
import {
  Typography,
  useTheme,
  Container,
  Stack
} from '@mui/material';
import { TrendingUp as TrendingUpIcon } from '@mui/icons-material';
import {
  StrategySelector,
  AccountPerformance,
  IndicatorTracking,
  Trades,
  Positions,
  TradingLogs
} from './components';

const LiveTradingPage = () => {
  const theme = useTheme();

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom sx={{ color: theme.palette.primary.main, fontWeight: 700, mb: 3 }}>
        <TrendingUpIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
        Live Trading
      </Typography>

      {/* Strategy Selection and Deployment */}
      <StrategySelector mode="live" />

      {/* Account Performance - Metrics and Equity Chart */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <AccountPerformance />
      </Stack>

      {/* Indicator Tracking */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <IndicatorTracking />
      </Stack>

      {/* Trading Logs */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <TradingLogs />
      </Stack>

      {/* Current Positions */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <Positions />
      </Stack>

      {/* Completed Trades */}
      <Trades />
    </Container>
  );
};

export default LiveTradingPage;
