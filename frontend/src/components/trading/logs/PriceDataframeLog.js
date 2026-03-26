import React, { useState } from 'react';
import { Box, Typography, useTheme, Chip, Button, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Collapse } from '@mui/material';
import AnalyticsIcon from '@mui/icons-material/Analytics';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';

const PriceDataframeLog = ({ log }) => {
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '';

  // log.data should hold the parsed JSON payload
  // structure: { type: "dataframe", title: "...", data: [...] }
  const payload = log.data || {};
  const tableData = payload.data || [];
  const title = payload.title || log.message || "Price Data";
  
  // Clean up message if it's just the JSON string
  const displayTitle = title.startsWith('{') ? 'Price Data Update' : title;

  // Render nothing if no data
  if (!Array.isArray(tableData) || tableData.length === 0) {
      return (
        <Box sx={{ mb: 1, borderBottom: `1px solid ${theme.palette.divider}`, pb: 1 }}>
            <Typography variant="body2">{log.message}</Typography>
        </Box>
      );
  }

  // Get columns from first row
  const columns = Object.keys(tableData[0]);

  return (
    <Box sx={{ mb: 1, borderBottom: `1px solid ${theme.palette.divider}`, pb: 1, p: 1, backgroundColor: 'rgba(0, 0, 0, 0.02)' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Typography component="span" variant="caption" sx={{ color: theme.palette.text.secondary, mr: 1 }}>
            {timestamp}
            </Typography>
            <Chip 
            icon={<AnalyticsIcon sx={{ fontSize: 14 }} />} 
            label="Data" 
            size="small" 
            color="info" 
            variant="outlined" 
            sx={{ height: 20, fontSize: '0.7rem', mr: 1 }}
            />
            <Typography variant="body2" sx={{ fontWeight: 500 }}>
                {displayTitle}
            </Typography>
        </Box>
        <Button
            size="small"
            onClick={() => setOpen(!open)}
            endIcon={open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
            sx={{ textTransform: 'none', fontSize: '0.75rem', py: 0 }}
        >
            {open ? 'Hide' : 'Show'} Table
        </Button>
      </Box>
      
      <Collapse in={open} timeout="auto" unmountOnExit>
        <TableContainer component={Paper} variant="outlined" sx={{ mt: 1, maxHeight: 300, overflow: 'auto' }}>
            <Table size="small" stickyHeader aria-label="price data table">
                <TableHead>
                    <TableRow>
                        {columns.map((col) => (
                            <TableCell key={col} sx={{ fontSize: '0.7rem', py: 0.5, fontWeight: 'bold' }}>{col}</TableCell>
                        ))}
                    </TableRow>
                </TableHead>
                <TableBody>
                    {tableData.slice(-10).map((row, idx) => ( // Show last 10 rows
                        <TableRow key={idx} hover>
                             {columns.map((col) => (
                                <TableCell key={`${idx}-${col}`} sx={{ fontSize: '0.7rem', py: 0.5 }}>
                                    {typeof row[col] === 'number' ? row[col].toFixed(4) : row[col]}
                                </TableCell>
                            ))}
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </TableContainer>
        <Typography variant="caption" sx={{ display: 'block', mt: 0.5, color: theme.palette.text.secondary, textAlign: 'right' }}>
            Showing last {Math.min(tableData.length, 10)} rows
        </Typography>
      </Collapse>
    </Box>
  );
};

export default PriceDataframeLog;
