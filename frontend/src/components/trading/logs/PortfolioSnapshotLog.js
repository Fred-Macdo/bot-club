import React, { useState } from 'react';
import { Box, Typography, useTheme, Chip, Button, Collapse, Paper } from '@mui/material';
import PieChartIcon from '@mui/icons-material/PieChart';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';

const PortfolioSnapshotLog = ({ log }) => {
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '';

  // Try to parse message if it contains "Portfolio before snapshot: {...}"
  let snapshotData = null;
  const prefix = "Portfolio before snapshot: ";
  if (log.message.startsWith(prefix)) {
      try {
          const jsonStr = log.message.substring(prefix.length).replace(/'/g, '"').replace(/None/g, 'null').replace(/False/g, 'false').replace(/True/g, 'true');
          // Basic cleanup for python string dump if not properly JSON
          // Ideally backend should send JSON object in data, but here we deal with string dump
          // If backend used model_dump(), it is a dict, but logged as string representation
          snapshotData = JSON.parse(jsonStr);
      } catch (e) {
          // Fallback if parsing fails
          // console.warn("Failed to parse portfolio snapshot", e);
      }
  }

  // If log.data contains object, prefer that
  if (log.data && typeof log.data === 'object' && !Array.isArray(log.data)) {
      snapshotData = log.data;
  }

  return (
    <Box sx={{ mb: 1, borderBottom: `1px solid ${theme.palette.divider}`, pb: 1, p: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Typography component="span" variant="caption" sx={{ color: theme.palette.text.secondary, mr: 1 }}>
            {timestamp}
            </Typography>
            <Chip 
            icon={<PieChartIcon sx={{ fontSize: 14 }} />} 
            label="Portfolio Snapshot" 
            size="small" 
            color="secondary" 
            variant="outlined" 
            sx={{ height: 20, fontSize: '0.7rem', mr: 1 }}
            />
        </Box>
        {snapshotData && (
            <Button
                size="small"
                onClick={() => setOpen(!open)}
                endIcon={open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
                sx={{ textTransform: 'none', fontSize: '0.75rem', py: 0 }}
            >
                {open ? 'Hide' : 'Show'} Details
            </Button>
        )}
      </Box>

        {!snapshotData && (
             <Typography variant="body2" sx={{ fontFamily: 'monospace', mt: 0.5, fontSize: '0.8rem', whiteSpace: 'pre-wrap' }}>
                {log.message}
            </Typography>
        )}
      
      {snapshotData && (
        <Collapse in={open} timeout="auto" unmountOnExit>
            <Paper variant="outlined" sx={{ mt: 1, p: 1, bgcolor: 'background.default', maxHeight: 300, overflow: 'auto' }}>
                 <pre style={{ margin: 0, fontSize: '0.7rem', fontFamily: 'monospace' }}>
                   {JSON.stringify(snapshotData, null, 2)}
                 </pre>
            </Paper>
        </Collapse>
      )}
    </Box>
  );
};

export default PortfolioSnapshotLog;
