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
  StrategyConfigPanel,
  AccountPerformance,
  IndicatorTracking,
  PriceDataframeCard,
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

      {/* Strategy Configuration Details */}
      <StrategyConfigPanel mode="live" />

      {/* Account Performance - Metrics and Equity Chart */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <AccountPerformance mode="live" />
      </Stack>

      {/* Indicator Tracking */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <IndicatorTracking mode="live" />
      </Stack>

      {/* Price Dataframe */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <PriceDataframeCard mode="live" />
      </Stack>

      {/* Trading Logs */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <TradingLogs mode="live" />
      </Stack>

      {/* Current Positions */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <Positions mode="live" />
      </Stack>

      {/* Completed Trades */}
      <Trades mode="live" />
    </Container>
  );
};

export default LiveTradingPage;
