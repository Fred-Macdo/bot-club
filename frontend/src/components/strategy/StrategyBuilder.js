import React, { useState } from 'react';
import { 
  Box, 
  Container, 
  Typography, 
  Tabs, 
  Tab, 
  Paper
} from '@mui/material';
import StrategyLibraryInterface from '../strategy/StrategyLibraryInterface';
import StrategyBuilderInterface from '../strategy/StrategyBuilderInterface';

// Strategy Center Main Page - Container for Strategy Library and Builder
const StrategyCenterPage = () => {
  const [activeTab, setActiveTab] = useState(0); // 0: Library, 1: Builder

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
          Strategy Center
        </Typography>
      </Box>

      {/* Main Tabs */}
      <Paper sx={{ borderRadius: 2, mb: 3 }}>
        <Tabs 
          value={activeTab} 
          onChange={(event, newValue) => setActiveTab(newValue)}
          sx={{ 
            borderBottom: 1, 
            borderColor: 'divider',
            '& .MuiTab-root': { 
              textTransform: 'none',
              fontSize: '1rem',
              fontWeight: 500
            }
          }}
        >
          <Tab label="Strategy Library" />
          <Tab label="Strategy Builder" />
        </Tabs>
      </Paper>

      {/* Tab Content */}
      <Box sx={{ mt: 3 }}>
        {activeTab === 0 && <StrategyLibraryInterface />}
        {activeTab === 1 && <StrategyBuilderInterface />}
      </Box>
    </Container>
  );
};

export default StrategyCenterPage;
