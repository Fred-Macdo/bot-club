import React from 'react';
import {
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  useTheme,
} from '@mui/material';
import {
  MonetizationOn as MonetizationOnIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Assessment as AssessmentIcon,
} from '@mui/icons-material';

const DashboardStatsCards = ({ stats }) => {
  const theme = useTheme();

  return (
    <Grid container spacing={2} sx={{ mb: 3 }}>
      <Grid item xs={12} sm={6} lg={12}>
        <Card>
          <CardContent sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <MonetizationOnIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
              <Typography variant="subtitle2">Total Return</Typography>
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 'bold', color: stats?.totalReturn >= 0 ? theme.palette.success.main : theme.palette.error.main }}>
              {stats?.totalReturn >= 0 ? '+' : ''}{stats?.totalReturn?.toFixed(2)}%
            </Typography>
            <Typography variant="body2" color="text.secondary">
              ${stats?.initialCapital?.toFixed(2)} → ${stats?.finalEquity?.toFixed(2)}
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
              {stats?.winRate?.toFixed(2)}%
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {stats?.winningTrades} / {stats?.totalTrades} trades
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
              -{stats?.maxDrawdown?.toFixed(2)}%
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Profit Factor: {stats?.profitFactor}
            </Typography>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
};

export default DashboardStatsCards;
