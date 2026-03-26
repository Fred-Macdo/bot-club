import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Chip,
  Stack,
  useTheme
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { useDeployedStrategy } from '../../../context/DeployedStrategyContext';

const Positions = () => {
  const theme = useTheme();
  
  const {
    positions
  } = useDeployedStrategy();

  const positionColumns = [
    { field: 'symbol', headerName: 'Symbol', width: 130 },
    { field: 'quantity', headerName: 'Quantity', width: 130, type: 'number' },
    { 
      field: 'entry_price', 
      headerName: 'Entry Price', 
      width: 150, 
      type: 'number',
      valueFormatter: (params) => {
        const val = params?.value !== undefined ? params.value : params;
        return val ? `$${Number(val).toFixed(4)}` : 'N/A';
      }
    },
    { 
      field: 'cost_basis', 
      headerName: 'Cost Basis', 
      width: 150, 
      type: 'number',
      valueFormatter: (params) => {
        const val = params?.value !== undefined ? params.value : params;
        return val ? `$${Number(val).toFixed(2)}` : 'N/A';
      }
    },
    { 
      field: 'entry_time', 
      headerName: 'Entry Time', 
      width: 180, 
      valueFormatter: (params) => {
        const val = params?.value !== undefined ? params.value : params;
        if (!val) return 'N/A';
        try {
          return new Date(val).toLocaleString();
        } catch {
          return 'N/A';
        }
      }
    },
    { 
      field: 'lot_id', 
      headerName: 'Lot ID', 
      width: 120,
      renderCell: (params) => (
        <Typography variant="caption" title={params.value}>
          {params.value ? `${params.value.substring(0, 8)}...` : ''}
        </Typography>
      )
    },
  ];

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Current Positions
        {positions && positions.length > 0 && (
          <Chip label={`${positions.length} open`} size="small" color="primary" sx={{ ml: 2 }} />
        )}
      </Typography>
      <Box sx={{ height: 250, width: '100%' }}>
        <DataGrid
          rows={positions || []}
          columns={positionColumns}
          getRowId={(row) => row.lot_id || row.symbol}
          pageSizeOptions={[5]}
          disableRowSelectionOnClick
          slots={{
            noRowsOverlay: () => (
              <Stack height="100%" alignItems="center" justifyContent="center">
                <Typography color="text.secondary">No open positions</Typography>
              </Stack>
            ),
          }}
          sx={{
            '& .MuiDataGrid-cell': { borderColor: theme.palette.divider },
            '& .MuiDataGrid-columnHeaders': { backgroundColor: theme.palette.background.default, borderColor: theme.palette.divider }
          }}
        />
      </Box>
    </Paper>
  );
};

export default Positions;
