// src/components/trading/PaperTradingPage.js
import React from 'react';
import {
  Typography,
  useTheme,
  Container,
  Stack
} from '@mui/material';
import { Assessment as AssessmentIcon } from '@mui/icons-material';
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

const PaperTradingPage = () => {
  const theme = useTheme();

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom sx={{ color: theme.palette.primary.main, fontWeight: 700, mb: 3 }}>
        <AssessmentIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
        Paper Trading
      </Typography>

      {/* Strategy Selection and Deployment */}
      <StrategySelector mode="paper" />

      {/* Strategy Configuration Details */}
      <StrategyConfigPanel mode="paper" />

      {/* Account Performance - Metrics and Equity Chart */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <AccountPerformance mode="paper" />
      </Stack>

      {/* Indicator Tracking */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <IndicatorTracking mode="paper" />
      </Stack>

      {/* Price Dataframe */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <PriceDataframeCard mode="paper" />
      </Stack>

      {/* Trading Logs */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <TradingLogs mode="paper" />
      </Stack>

      {/* Current Positions */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <Positions mode="paper" />
      </Stack>

      {/* Completed Trades */}
      <Trades mode="paper" />
    </Container>
  );
};

export default PaperTradingPage;
