import React from 'react';
import {
  Paper,
  Typography,
  TableContainer,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  TableSortLabel,
  Chip,
  useTheme,
} from '@mui/material';

const RecentActivityTable = ({ trades, orderBy, order, handleRequestSort }) => {
  const theme = useTheme();
  const sortedTrades = trades.slice().sort((a, b) => {
    const isAsc = order === 'asc';
    if (a[orderBy] < b[orderBy]) {
      return isAsc ? -1 : 1;
    }
    if (a[orderBy] > b[orderBy]) {
      return isAsc ? 1 : -1;
    }
    return 0;
  });

  return (
    <Paper sx={{ p: 3, borderRadius: 2, height: '500px', display: 'flex', flexDirection: 'column' }}>
      <Typography variant="h6" gutterBottom>
        Recent Account Activity
      </Typography>
      <TableContainer sx={{ flexGrow: 1, maxHeight: 'none' }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell>
                <TableSortLabel
                  active={orderBy === 'symbol'}
                  direction={orderBy === 'symbol' ? order : 'asc'}
                  onClick={() => handleRequestSort('symbol')}
                >
                  Symbol
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={orderBy === 'side'}
                  direction={orderBy === 'side' ? order : 'asc'}
                  onClick={() => handleRequestSort('side')}
                >
                  Side
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={orderBy === 'entryDate'}
                  direction={orderBy === 'entryDate' ? order : 'asc'}
                  onClick={() => handleRequestSort('entryDate')}
                >
                  Date
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={orderBy === 'entryPrice'}
                  direction={orderBy === 'entryPrice' ? order : 'asc'}
                  onClick={() => handleRequestSort('entryPrice')}
                >
                  Price
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={orderBy === 'shares'}
                  direction={orderBy === 'shares' ? order : 'asc'}
                  onClick={() => handleRequestSort('shares')}
                >
                  Shares
                </TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={orderBy === 'pnl'}
                  direction={orderBy === 'pnl' ? order : 'asc'}
                  onClick={() => handleRequestSort('pnl')}
                >
                  Net P&L ($)
                </TableSortLabel>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedTrades.slice(0, 50).map((trade) => (
              <TableRow
                key={trade.id}
                sx={{
                  '&:nth-of-type(odd)': { bgcolor: theme.palette.action.hover },
                  bgcolor: trade.pnl > 0 ? 'rgba(46, 125, 50, 0.04)' : 'rgba(211, 47, 47, 0.04)'
                }}
              >
                <TableCell>
                  <Chip label={trade.symbol} size="small" sx={{ bgcolor: theme.palette.primary.light, color: theme.palette.primary.contrastText, fontSize: '0.75rem', height: 20 }} />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ color: trade.side === 'buy' ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>
                    {trade.side.toUpperCase()}
                  </Typography>
                </TableCell>
                <TableCell>{trade.entryDate.toLocaleDateString()}</TableCell>
                <TableCell>${trade.entryPrice.toFixed(2)}</TableCell>
                <TableCell>{trade.shares}</TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ color: trade.pnl > 0 ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>
                    {trade.pnl > 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );
};

export default RecentActivityTable;
