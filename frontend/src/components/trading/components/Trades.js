import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  useTheme
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { useTradingMode } from '../../../context/DeployedStrategyContext';

const Trades = ({ mode = 'paper' }) => {
  const theme = useTheme();
  
  const {
    completedTrades
  } = useTradingMode(mode);

  const tradeColumns = [
    { field: 'trade_id', headerName: 'ID', width: 100,
      valueGetter: (value, row) => {
        const id = row?.trade_id || row?.id || '';
        return typeof id === 'string' && id.length > 8 ? id.slice(0, 8) + '...' : id;
      }
    },
    { field: 'symbol', headerName: 'Symbol', width: 100 },
    { 
      field: 'side', 
      headerName: 'Side', 
      width: 80, 
      valueGetter: (value, row) => row?.side || 'SELL',
      renderCell: (params) => {
        const val = params?.value || 'SELL';
        return <Chip label={val} color={val === 'BUY' ? 'success' : 'error'} size="small"/>;
      }
    },
    { 
      field: 'quantity', 
      headerName: 'Quantity', 
      width: 110, 
      type: 'number',
      valueGetter: (value, row) => row?.quantity ?? null,
      valueFormatter: (value) => {
        if (value == null) return 'N/A';
        try { return Number(value).toFixed(4); } catch { return 'N/A'; }
      }
    },
    { 
      field: 'entry_price', 
      headerName: 'Entry Price', 
      width: 120, 
      type: 'number',
      valueGetter: (value, row) => row?.entry_price ?? row?.entryPrice ?? null,
      valueFormatter: (value) => {
        if (value == null) return 'N/A';
        try { return `$${Number(value).toFixed(4)}`; } catch { return 'N/A'; }
      }
    },
    { 
      field: 'exit_price', 
      headerName: 'Exit Price', 
      width: 120, 
      type: 'number',
      valueGetter: (value, row) => row?.exit_price ?? row?.exitPrice ?? null,
      valueFormatter: (value) => {
        if (value == null) return 'N/A';
        try { return `$${Number(value).toFixed(4)}`; } catch { return 'N/A'; }
      }
    },
    { 
      field: 'entry_time', 
      headerName: 'Entry Time', 
      width: 180, 
      type: 'dateTime', 
      valueGetter: (value, row) => {
        const t = row?.entry_time ?? row?.entryTime;
        if (!t) return null;
        try { return new Date(t); } catch { return null; }
      },
      valueFormatter: (value) => {
        if (!value) return 'N/A';
        try { return value.toLocaleString(); } catch { return 'N/A'; }
      }
    },
    { 
      field: 'exit_time', 
      headerName: 'Exit Time', 
      width: 180, 
      type: 'dateTime', 
      valueGetter: (value, row) => {
        const t = row?.exit_time ?? row?.exitTime;
        if (!t) return null;
        try { return new Date(t); } catch { return null; }
      },
      valueFormatter: (value) => {
        if (!value) return 'N/A';
        try { return value.toLocaleString(); } catch { return 'N/A'; }
      }
    },
    { 
      field: 'realized_pnl', 
      headerName: 'P&L', 
      width: 120, 
      type: 'number', 
      valueGetter: (value, row) => row?.realized_pnl ?? row?.pnl ?? null,
      renderCell: (params) => {
        if (params?.value == null) return <Typography variant="body2">N/A</Typography>;
        try {
          const pnlValue = Number(params.value);
          return (
            <Typography 
              variant="body2" 
              sx={{ 
                color: pnlValue >= 0 ? theme.palette.success.main : theme.palette.error.main, 
                fontWeight: 'bold' 
              }}
            >
              ${pnlValue.toFixed(2)}
            </Typography>
          );
        } catch {
          return <Typography variant="body2">N/A</Typography>;
        }
      }
    },
    { 
      field: 'exit_reason', 
      headerName: 'Reason', 
      width: 140, 
      valueGetter: (value, row) => row?.exit_reason || row?.status || 'Closed',
    }
  ];

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Completed Trades 
        {completedTrades && completedTrades.length > 0 && (
          <Chip label={`${completedTrades.length} trades`} size="small" sx={{ ml: 2 }} />
        )}
      </Typography>
      <Box sx={{ height: 400, width: '100%' }}>
        <DataGrid 
          rows={completedTrades || []} 
          columns={tradeColumns} 
          getRowId={(row) => row.trade_id || row.lot_id || row.id || Math.random().toString(36)}
          pageSize={5} 
          rowsPerPageOptions={[5, 10, 25]} 
          disableSelectionOnClick 
          sx={{ 
            '& .MuiDataGrid-cell': { borderColor: theme.palette.divider }, 
            '& .MuiDataGrid-columnHeaders': { backgroundColor: theme.palette.background.default, borderColor: theme.palette.divider } 
          }} 
        />
      </Box>
    </Paper>
  );
};

export default Trades;
