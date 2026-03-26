import React, { useMemo } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  useTheme
} from '@mui/material';
import Plot from 'react-plotly.js';
import { useDeployedStrategy } from '../../../context/DeployedStrategyContext';

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
    } else if (lower.startsWith('bb_') || lower.startsWith('bollinger') || lower.startsWith('bband')) {
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

const LINE_COLORS = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
  '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
];

const IndicatorTracking = () => {
  const theme = useTheme();

  const { isDeployed, indicatorData } = useDeployedStrategy();

  const charts = useMemo(() => {
    if (!indicatorData || Object.keys(indicatorData).length === 0) return [];

    const allCharts = [];

    Object.entries(indicatorData).forEach(([symbol, data]) => {
      if (!data.columns || !data.rows || data.rows.length === 0) return;

      const groups = groupColumns(data.columns);
      const rows = data.rows;
      const timestamps = rows.map(r => r.datetime ? new Date(r.datetime) : null).filter(Boolean);
      const closeValues = rows.map(r => r.close);

      Object.entries(groups).forEach(([groupName, { cols, overlay }]) => {
        const traces = [];

        // For overlay indicators, include close as reference
        if (overlay && closeValues.some(v => v != null)) {
          traces.push({
            x: timestamps,
            y: closeValues,
            type: 'scatter',
            mode: 'lines',
            name: 'Close',
            line: { color: theme.palette.text.secondary, width: 1, dash: 'dot' },
          });
        }

        cols.forEach((col, idx) => {
          const values = rows.map(r => r[col]);
          if (values.every(v => v == null)) return;

          const isHistogram = col.toLowerCase().includes('histogram') || col.toLowerCase().includes('hist');

          traces.push({
            x: timestamps,
            y: values,
            type: isHistogram ? 'bar' : 'scatter',
            mode: isHistogram ? undefined : 'lines',
            name: col,
            line: isHistogram ? undefined : {
              color: LINE_COLORS[idx % LINE_COLORS.length],
              width: 2,
            },
            marker: isHistogram ? {
              color: values.map(v => v >= 0 ? theme.palette.success.main : theme.palette.error.main),
            } : undefined,
          });
        });

        if (traces.length > 0) {
          allCharts.push({
            key: `${symbol}-${groupName}`,
            title: `${groupName}${Object.keys(indicatorData).length > 1 ? ` (${symbol})` : ''}`,
            traces,
            overlay,
          });
        }
      });
    });

    return allCharts;
  }, [indicatorData, theme]);

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

  if (charts.length === 0) {
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
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Indicator Tracking
        <Chip
          label={`${charts.length} indicator${charts.length > 1 ? 's' : ''}`}
          size="small"
          color="primary"
          sx={{ ml: 2 }}
        />
      </Typography>

      {charts.map(chart => (
        <Box key={chart.key} sx={{ mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 0.5, fontWeight: 'bold' }}>
            {chart.title}
          </Typography>
          <Plot
            data={chart.traces}
            layout={{
              height: 260,
              margin: { l: 50, r: 20, b: 40, t: 10 },
              xaxis: { type: 'date', gridcolor: theme.palette.divider },
              yaxis: { gridcolor: theme.palette.divider, tickformat: chart.overlay ? '$,.4f' : ',.4f' },
              plot_bgcolor: theme.palette.background.paper,
              paper_bgcolor: theme.palette.background.paper,
              font: { color: theme.palette.text.primary, size: 11 },
              legend: { orientation: 'h', yanchor: 'bottom', y: 1.02, xanchor: 'left', x: 0, font: { size: 10 } },
              showlegend: true,
            }}
            style={{ width: '100%' }}
            config={{ responsive: true, displaylogo: false, displayModeBar: false }}
          />
        </Box>
      ))}
    </Paper>
  );
};

export default IndicatorTracking;
