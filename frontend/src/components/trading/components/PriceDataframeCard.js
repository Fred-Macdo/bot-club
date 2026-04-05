import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  useTheme
} from '@mui/material';
import AnalyticsIcon from '@mui/icons-material/Analytics';
import { useTradingMode } from '../../../context/DeployedStrategyContext';

const PriceDataframeCard = ({ mode = 'paper' }) => {
  const theme = useTheme();
  const { isDeployed, priceDataframes } = useTradingMode(mode);
  const [activeTab, setActiveTab] = useState(0);
  const tableEndRef = useRef(null);

  const symbols = useMemo(() => Object.keys(priceDataframes || {}), [priceDataframes]);

  // Auto-scroll to bottom when new rows arrive
  useEffect(() => {
    if (tableEndRef.current) {
      tableEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [priceDataframes, activeTab]);

  if (!isDeployed) {
    return (
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          <AnalyticsIcon sx={{ mr: 1, verticalAlign: 'middle', fontSize: 20 }} />
          Price Data
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 100, color: theme.palette.text.secondary }}>
          Deploy a strategy to see price data
        </Box>
      </Paper>
    );
  }

  if (symbols.length === 0) {
    return (
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          <AnalyticsIcon sx={{ mr: 1, verticalAlign: 'middle', fontSize: 20 }} />
          Price Data
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 100, color: theme.palette.text.secondary }}>
          Waiting for price data...
        </Box>
      </Paper>
    );
  }

  const currentSymbol = symbols[activeTab] || symbols[0];
  const rows = priceDataframes[currentSymbol] || [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  // Separate OHLCV columns and indicator columns for visual distinction
  const ohlcvSet = new Set(['symbol', 'datetime', 'date', 'open', 'high', 'low', 'close', 'volume']);
  const ohlcvCols = columns.filter(c => ohlcvSet.has(c.toLowerCase()));
  const indicatorCols = columns.filter(c => !ohlcvSet.has(c.toLowerCase()));

  const formatCell = (val, col) => {
    if (val == null) return '—';
    if (typeof val === 'number') {
      // Use fewer decimals for volume
      if (col.toLowerCase() === 'volume') return val.toLocaleString();
      return val.toFixed(4);
    }
    return String(val);
  };

  return (
    <Paper sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="h6">
          <AnalyticsIcon sx={{ mr: 1, verticalAlign: 'middle', fontSize: 20 }} />
          Price Data
          <Chip
            label={`${rows.length} row${rows.length !== 1 ? 's' : ''}`}
            size="small"
            color="info"
            sx={{ ml: 1.5, height: 22, fontSize: '0.7rem' }}
          />
        </Typography>
      </Box>

      {/* Symbol Tabs */}
      {symbols.length > 1 && (
        <Tabs
          value={activeTab}
          onChange={(_, v) => setActiveTab(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ mb: 1, minHeight: 36, '& .MuiTab-root': { minHeight: 36, py: 0.5, fontSize: '0.8rem' } }}
        >
          {symbols.map((sym, i) => (
            <Tab key={sym} label={sym} />
          ))}
        </Tabs>
      )}

      <TableContainer sx={{ maxHeight: 420, overflow: 'auto' }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              {ohlcvCols.map(col => (
                <TableCell
                  key={col}
                  sx={{ fontWeight: 'bold', fontSize: '0.7rem', py: 0.5, whiteSpace: 'nowrap' }}
                >
                  {col}
                </TableCell>
              ))}
              {indicatorCols.map(col => (
                <TableCell
                  key={col}
                  sx={{
                    fontWeight: 'bold',
                    fontSize: '0.7rem',
                    py: 0.5,
                    whiteSpace: 'nowrap',
                    color: theme.palette.info.main,
                    borderLeft: indicatorCols.indexOf(col) === 0 ? `2px solid ${theme.palette.divider}` : undefined,
                  }}
                >
                  {col}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row, idx) => (
              <TableRow key={idx} hover>
                {ohlcvCols.map(col => (
                  <TableCell key={`${idx}-${col}`} sx={{ fontSize: '0.7rem', py: 0.25, fontFamily: 'monospace' }}>
                    {formatCell(row[col], col)}
                  </TableCell>
                ))}
                {indicatorCols.map((col, ci) => (
                  <TableCell
                    key={`${idx}-${col}`}
                    sx={{
                      fontSize: '0.7rem',
                      py: 0.25,
                      fontFamily: 'monospace',
                      borderLeft: ci === 0 ? `2px solid ${theme.palette.divider}` : undefined,
                    }}
                  >
                    {formatCell(row[col], col)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
            <tr ref={tableEndRef} />
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="caption" sx={{ display: 'block', mt: 0.5, color: theme.palette.text.secondary, textAlign: 'right' }}>
        Showing last {rows.length} of max 100 rows {currentSymbol && `for ${currentSymbol}`}
      </Typography>
    </Paper>
  );
};

export default PriceDataframeCard;
