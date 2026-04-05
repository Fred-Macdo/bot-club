import React, { useMemo, useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  useTheme
} from '@mui/material';
import { ExpandMore as ExpandMoreIcon } from '@mui/icons-material';
import FinancialChart from './FinancialChart';
import { useTradingMode } from '../../../context/DeployedStrategyContext';

/**
 * Group indicator columns into logical chart groups.
 * E.g. macd, macd_signal, macd_histogram → one "MACD" chart
 *      bb_upper, bb_middle, bb_lower   → one "Bollinger Bands" chart
 *      sma_5, sma_20                   → one "SMA" chart (overlaid on close)
 */
const groupColumns = (columns) => {
  const groups = {};

  columns.forEach(col => {
    const lower = col.toLowerCase();

    if (lower.startsWith('macd')) {
      if (!groups['MACD']) groups['MACD'] = { cols: [], overlay: false };
      groups['MACD'].cols.push(col);
    } else if (lower.startsWith('bb_') || lower.startsWith('bollinger') || lower.startsWith('bband')
               || lower === 'upperband' || lower === 'middleband' || lower === 'lowerband') {
      if (!groups['Bollinger Bands']) groups['Bollinger Bands'] = { cols: [], overlay: true };
      groups['Bollinger Bands'].cols.push(col);
    } else if (lower.startsWith('rsi')) {
      if (!groups['RSI']) groups['RSI'] = { cols: [], overlay: false };
      groups['RSI'].cols.push(col);
    } else if (lower.startsWith('sma')) {
      if (!groups['SMA']) groups['SMA'] = { cols: [], overlay: true };
      groups['SMA'].cols.push(col);
    } else if (lower.startsWith('ema')) {
      if (!groups['EMA']) groups['EMA'] = { cols: [], overlay: true };
      groups['EMA'].cols.push(col);
    } else if (lower.startsWith('atr')) {
      if (!groups['ATR']) groups['ATR'] = { cols: [], overlay: false };
      groups['ATR'].cols.push(col);
    } else if (lower.startsWith('adx')) {
      if (!groups['ADX']) groups['ADX'] = { cols: [], overlay: false };
      groups['ADX'].cols.push(col);
    } else if (lower.startsWith('mfi')) {
      if (!groups['MFI']) groups['MFI'] = { cols: [], overlay: false };
      groups['MFI'].cols.push(col);
    } else if (lower.startsWith('cci')) {
      if (!groups['CCI']) groups['CCI'] = { cols: [], overlay: false };
      groups['CCI'].cols.push(col);
    } else if (lower.startsWith('obv')) {
      if (!groups['OBV']) groups['OBV'] = { cols: [], overlay: false };
      groups['OBV'].cols.push(col);
    } else if (lower.startsWith('vwap')) {
      if (!groups['VWAP']) groups['VWAP'] = { cols: [], overlay: true };
      groups['VWAP'].cols.push(col);
    } else {
      const name = col.toUpperCase();
      if (!groups[name]) groups[name] = { cols: [], overlay: false };
      groups[name].cols.push(col);
    }
  });

  return groups;
};

const IndicatorTracking = ({ mode = 'paper' }) => {
  const theme = useTheme();

  const { isDeployed, indicatorData } = useTradingMode(mode);

  // Build per-(symbol × indicator group) accordion items
  const accordionItems = useMemo(() => {
    if (!indicatorData || Object.keys(indicatorData).length === 0) return [];

    const items = [];

    Object.entries(indicatorData).forEach(([symbol, symbolData]) => {
      if (!symbolData.columns || !symbolData.rows || symbolData.rows.length === 0) return;

      const groups = groupColumns(symbolData.columns);

      // Transform rows: datetime string → Date object, ensure OHLCV are numbers
      const chartRows = symbolData.rows
        .map((r) => {
          const date = r.datetime ? new Date(r.datetime) : null;
          if (!date || isNaN(date.getTime())) return null;
          return {
            ...r,
            date,
            open: Number(r.open) || 0,
            high: Number(r.high) || 0,
            low: Number(r.low) || 0,
            close: Number(r.close) || 0,
            volume: Number(r.volume) || 0,
          };
        })
        .filter(Boolean);

      if (chartRows.length === 0) return;

      Object.entries(groups).forEach(([groupName, { cols, overlay }]) => {
        // Only include columns that have at least one non-null value
        const activeCols = cols.filter((col) =>
          chartRows.some((r) => r[col] != null)
        );
        if (activeCols.length === 0 && !overlay) return;

        items.push({
          key: `${symbol}-${groupName}`,
          title: `${groupName} — ${symbol}`,
          symbol,
          groupName,
          cols: activeCols,
          overlay,
          data: chartRows,
        });
      });
    });

    return items;
  }, [indicatorData]);

  // Track which accordion is expanded (first one by default)
  const [expanded, setExpanded] = useState(null);

  const handleAccordionChange = (panel) => (_, isExpanded) => {
    setExpanded(isExpanded ? panel : null);
  };

  // Auto-expand first accordion when items appear
  useMemo(() => {
    if (accordionItems.length > 0 && expanded === null) {
      setExpanded(accordionItems[0].key);
    }
  }, [accordionItems.length]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isDeployed) {
    return (
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>Indicator Tracking</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 150, color: theme.palette.text.secondary }}>
          Deploy a strategy to see indicator charts
        </Box>
      </Paper>
    );
  }

  if (accordionItems.length === 0) {
    return (
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>Indicator Tracking</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 150, color: theme.palette.text.secondary }}>
          Waiting for indicator data...
        </Box>
      </Paper>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Typography variant="h6" sx={{ mb: 0.5 }}>Indicator Tracking</Typography>
      {accordionItems.map(item => (
        <Accordion
          key={item.key}
          expanded={expanded === item.key}
          onChange={handleAccordionChange(item.key)}
          disableGutters
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="subtitle1" fontWeight="bold">{item.title}</Typography>
              <Chip
                label={item.overlay ? 'overlay' : 'standalone'}
                size="small"
                color={item.overlay ? 'primary' : 'secondary'}
                variant="outlined"
              />
            </Box>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 1, overflow: 'hidden' }}>
            <FinancialChart
              data={item.data}
              indicatorCols={item.cols}
              overlay={item.overlay}
              groupName={item.groupName}
              symbol={item.symbol}
              height={item.overlay ? 380 : 260}
            />
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
};

export default IndicatorTracking;
