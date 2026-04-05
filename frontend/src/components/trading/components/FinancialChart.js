import React, { useMemo } from 'react';
import { useTheme, Box, Typography } from '@mui/material';
import { LineChart } from '@mui/x-charts/LineChart';
import { ChartsReferenceLine } from '@mui/x-charts/ChartsReferenceLine';

const LINE_COLORS = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
  '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
  '#17becf', '#bcbd22',
];

/**
 * FinancialChart — MUI X Charts wrapper for indicator data.
 *
 * Props:
 *   data           – array of { date: Date, open, high, low, close, volume, ...indicators }
 *   indicatorCols  – array of indicator column names to plot
 *   overlay        – boolean; if true, renders close price + indicators overlaid
 *   groupName      – e.g. "SMA", "MACD", "RSI"
 *   symbol         – ticker symbol
 *   height         – chart height in px
 */
const FinancialChart = ({ data, indicatorCols, overlay, groupName, symbol, height: heightProp }) => {
  const theme = useTheme();
  const height = heightProp || (overlay ? 380 : 260);
  const isRSI = groupName === 'RSI';

  const series = useMemo(() => {
    const list = [];
    let colorIdx = 0;

    // Overlay mode: add close price line
    if (overlay) {
      list.push({
        dataKey: 'close',
        label: `${symbol} Close`,
        color: theme.palette.text.primary,
        showMark: false,
        valueFormatter: (v) => v != null ? `$${Number(v).toFixed(4)}` : '–',
      });
    }

    indicatorCols
      .filter((col) => !col.toLowerCase().endsWith('_prev'))
      .forEach((col) => {
      const colLower = col.toLowerCase();
      const isHist = colLower.includes('histogram') || colLower.includes('hist');

      if (isHist) {
        // Render histogram as filled area from zero
        list.push({
          dataKey: col,
          label: col,
          color: theme.palette.info.main,
          showMark: false,
          area: true,
          connectNulls: true,
          valueFormatter: (v) => v != null ? Number(v).toFixed(6) : '–',
        });
      } else {
        list.push({
          dataKey: col,
          label: col,
          color: LINE_COLORS[colorIdx % LINE_COLORS.length],
          showMark: false,
          connectNulls: true,
          valueFormatter: (v) => {
            if (v == null) return '–';
            const n = Number(v);
            return overlay ? `$${n.toFixed(4)}` : n.toFixed(4);
          },
        });
        colorIdx++;
      }
    });

    return list;
  }, [indicatorCols, overlay, symbol, theme]);

  if (!data || data.length === 0) {
    return (
      <Box sx={{ width: '100%', height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography variant="body2" color="text.secondary">No data</Typography>
      </Box>
    );
  }

  const xAxis = [{
    dataKey: 'date',
    scaleType: 'time',
    valueFormatter: (d) =>
      d instanceof Date
        ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '',
  }];

  const yAxis = overlay
    ? [{ valueFormatter: (v) => `$${Number(v).toFixed(2)}` }]
    : [{}];

  return (
    <LineChart
      dataset={data}
      series={series}
      xAxis={xAxis}
      yAxis={yAxis}
      height={height}
      grid={{ horizontal: true }}
      slotProps={{
        legend: {
          direction: 'row',
          position: { vertical: 'top', horizontal: 'middle' },
        },
        tooltip: {
          trigger: 'axis',
        },
      }}
    >
      {isRSI && (
        <>
          <ChartsReferenceLine
            y={70}
            lineStyle={{ stroke: theme.palette.error.main, strokeDasharray: '5 3' }}
            label="Overbought (70)"
            labelStyle={{ fill: theme.palette.error.main, fontSize: 11 }}
          />
          <ChartsReferenceLine
            y={30}
            lineStyle={{ stroke: theme.palette.success.main, strokeDasharray: '5 3' }}
            label="Oversold (30)"
            labelStyle={{ fill: theme.palette.success.main, fontSize: 11 }}
          />
        </>
      )}
    </LineChart>
  );
};

export default React.memo(FinancialChart);
