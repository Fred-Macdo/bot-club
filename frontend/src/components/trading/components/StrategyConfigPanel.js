import React, { useState } from 'react';
import {
  Box,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Grid,
  Divider,
  useTheme
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Settings as SettingsIcon,
  TrendingUp as TrendingUpIcon,
  ExitToApp as ExitToAppIcon,
  Shield as ShieldIcon,
  ShowChart as ShowChartIcon,
  Schedule as ScheduleIcon,
  Warning as WarningIcon
} from '@mui/icons-material';
import { useTradingMode } from '../../../context/DeployedStrategyContext';

const StrategyConfigPanel = ({ mode = 'paper' }) => {
  const theme = useTheme();
  const { deployedStrategy, isDeployed, sessionHealth } = useTradingMode(mode);

  // Use the deployed strategy's config, or the selected strategy's config
  const strategy = deployedStrategy;
  const config = strategy?.config;

  if (!strategy) {
    return null;
  }

  const symbols = config?.symbols || [];
  const timeframe = config?.timeframe || 'N/A';
  const indicators = config?.indicators || [];
  const entryConditions = config?.entry_conditions || [];
  const exitConditions = config?.exit_conditions || [];
  const riskManagement = config?.risk_management || {};

  const formatComparison = (comp) => {
    const map = {
      above: '>', below: '<', crosses_above: '↗ crosses above',
      crosses_below: '↘ crosses below', equals: '=', gte: '≥', lte: '≤'
    };
    return map[comp] || comp;
  };

  const formatValue = (val) => {
    if (typeof val === 'number') return val.toLocaleString();
    if (typeof val === 'string') return val.toUpperCase();
    return String(val);
  };

  const formatPercent = (val) => {
    if (val == null) return 'N/A';
    return typeof val === 'number' && val < 1 ? `${(val * 100).toFixed(1)}%` : `${val}%`;
  };

  return (
    <Accordion defaultExpanded={false} sx={{ mb: 3 }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
          <SettingsIcon color="action" />
          <Typography variant="h6">Strategy Configuration</Typography>
          {isDeployed && (
            <Chip label={strategy.name} color="primary" size="small" variant="outlined" sx={{ ml: 'auto', mr: 2 }} />
          )}
          {!isDeployed && strategy && (
            <Chip label={strategy.name} size="small" variant="outlined" sx={{ ml: 'auto', mr: 2 }} />
          )}
        </Box>
      </AccordionSummary>
      <AccordionDetails>
        {sessionHealth === 'stale' && (
          <Paper variant="outlined" sx={{ p: 1.5, mb: 2, display: 'flex', alignItems: 'center', gap: 1, bgcolor: 'warning.dark', borderColor: 'warning.main' }}>
            <WarningIcon color="warning" fontSize="small" />
            <Typography variant="body2" color="warning.main">
              Session appears stale — the trading task may have stopped. Consider stopping and redeploying.
            </Typography>
          </Paper>
        )}
        {!config ? (
          <Typography color="text.secondary" sx={{ fontStyle: 'italic' }}>
            No configuration data available for this strategy.
          </Typography>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            {/* Symbols & Timeframe */}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <ShowChartIcon fontSize="small" color="primary" />
                <Typography variant="subtitle2" fontWeight="bold">Instruments</Typography>
              </Box>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
                {symbols.map(s => (
                  <Chip key={s} label={s} size="small" color="primary" variant="outlined" />
                ))}
                <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <ScheduleIcon fontSize="small" color="action" />
                  <Chip label={timeframe.toUpperCase()} size="small" color="secondary" variant="outlined" />
                </Box>
              </Box>
            </Box>

            <Divider />

            {/* Indicators */}
            {indicators.length > 0 && (
              <Box>
                <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>
                  Indicators ({indicators.length})
                </Typography>
                <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 200 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', fontSize: '0.75rem' }}>Name</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', fontSize: '0.75rem' }}>Parameters</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {indicators.map((ind, i) => (
                        <TableRow key={i} hover>
                          <TableCell sx={{ fontSize: '0.8rem' }}>
                            <Chip label={ind.name} size="small" color="info" variant="outlined" sx={{ height: 22, fontSize: '0.7rem' }} />
                          </TableCell>
                          <TableCell sx={{ fontSize: '0.8rem', fontFamily: 'monospace' }}>
                            {ind.params
                              ? Object.entries(ind.params).map(([k, v]) => `${k}: ${v}`).join(', ')
                              : '—'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            )}

            <Divider />

            {/* Entry Conditions */}
            {entryConditions.length > 0 && (
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <TrendingUpIcon fontSize="small" color="success" />
                  <Typography variant="subtitle2" fontWeight="bold" color="success.main">
                    Entry Conditions ({entryConditions.length})
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                  {entryConditions.map((cond, i) => (
                    <Paper key={i} variant="outlined" sx={{ px: 1.5, py: 0.75, display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Chip label={String(cond.indicator).toUpperCase()} size="small" sx={{ height: 22, fontSize: '0.7rem', fontWeight: 'bold' }} />
                      <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                        {formatComparison(cond.comparison)}
                      </Typography>
                      <Chip label={formatValue(cond.value)} size="small" variant="outlined" sx={{ height: 22, fontSize: '0.7rem' }} />
                    </Paper>
                  ))}
                </Box>
              </Box>
            )}

            {/* Exit Conditions */}
            {exitConditions.length > 0 && (
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <ExitToAppIcon fontSize="small" color="error" />
                  <Typography variant="subtitle2" fontWeight="bold" color="error.main">
                    Exit Conditions ({exitConditions.length})
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                  {exitConditions.map((cond, i) => (
                    <Paper key={i} variant="outlined" sx={{ px: 1.5, py: 0.75, display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Chip label={String(cond.indicator).toUpperCase()} size="small" sx={{ height: 22, fontSize: '0.7rem', fontWeight: 'bold' }} />
                      <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                        {formatComparison(cond.comparison)}
                      </Typography>
                      <Chip label={formatValue(cond.value)} size="small" variant="outlined" sx={{ height: 22, fontSize: '0.7rem' }} />
                    </Paper>
                  ))}
                </Box>
              </Box>
            )}

            <Divider />

            {/* Risk Management */}
            {Object.keys(riskManagement).length > 0 && (
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <ShieldIcon fontSize="small" color="warning" />
                  <Typography variant="subtitle2" fontWeight="bold">Risk Management</Typography>
                </Box>
                <Grid container spacing={1.5}>
                  {riskManagement.position_sizing_method && (
                    <Grid item xs={6} sm={4} md={3}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                        <Typography variant="caption" color="text.secondary">Method</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {riskManagement.position_sizing_method}
                        </Typography>
                      </Paper>
                    </Grid>
                  )}
                  {riskManagement.risk_per_trade != null && (
                    <Grid item xs={6} sm={4} md={3}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                        <Typography variant="caption" color="text.secondary">Risk / Trade</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatPercent(riskManagement.risk_per_trade)}
                        </Typography>
                      </Paper>
                    </Grid>
                  )}
                  {riskManagement.stop_loss != null && (
                    <Grid item xs={6} sm={4} md={3}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                        <Typography variant="caption" color="text.secondary">Stop Loss</Typography>
                        <Typography variant="body2" fontWeight="bold" color="error.main">
                          {formatPercent(riskManagement.stop_loss)}
                        </Typography>
                      </Paper>
                    </Grid>
                  )}
                  {riskManagement.take_profit != null && (
                    <Grid item xs={6} sm={4} md={3}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                        <Typography variant="caption" color="text.secondary">Take Profit</Typography>
                        <Typography variant="body2" fontWeight="bold" color="success.main">
                          {formatPercent(riskManagement.take_profit)}
                        </Typography>
                      </Paper>
                    </Grid>
                  )}
                  {riskManagement.max_position_size != null && (
                    <Grid item xs={6} sm={4} md={3}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                        <Typography variant="caption" color="text.secondary">Max Position</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          ${riskManagement.max_position_size.toLocaleString()}
                        </Typography>
                      </Paper>
                    </Grid>
                  )}
                  {riskManagement.atr_multiplier != null && (
                    <Grid item xs={6} sm={4} md={3}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center' }}>
                        <Typography variant="caption" color="text.secondary">ATR Multiplier</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {riskManagement.atr_multiplier}x
                        </Typography>
                      </Paper>
                    </Grid>
                  )}
                </Grid>
              </Box>
            )}
          </Box>
        )}
      </AccordionDetails>
    </Accordion>
  );
};

export default StrategyConfigPanel;
