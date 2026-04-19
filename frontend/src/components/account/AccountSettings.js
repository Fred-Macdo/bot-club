// src/components/account/AccountSettings.js
import React, { useState } from 'react';
import { 
  Box, 
  Typography, 
  Paper, 
  Tabs, 
  Tab,
  useTheme 
} from '@mui/material';
//import { useAuth } from '../auth/AuthContext';
import ApiConfigForm from './ApiConfigForm';
import ProfileSettings from './ProfileSettingsForm';
import SecuritySettingsForm from './SecuritySettingsForm';

const AccountSettings = () => {
  const theme = useTheme();
  const [activeTab, setActiveTab] = useState(0);
  
  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };
  
  return (
    <Box>

      <Paper elevation={1} sx={{ borderRadius: 2 }}>
        <Tabs 
          value={activeTab} 
          onChange={handleTabChange}
          sx={{ 
            borderBottom: 1, 
            borderColor: 'divider',
            bgcolor: theme.palette.primary.main,
            borderRadius: '8px 8px 0 0',
            '& .MuiTab-root': { color: theme.palette.secondary.main },
            '& .Mui-selected': { color: '#ffffff !important' }
                  
          }}
          TabIndicatorProps={{
            style: {
              backgroundColor: theme.palette.secondary.main, // Change indicator color
              height: 4,
              borderRadius: 2,
            }
          }}
        >
          <Tab label="Profile" />
          <Tab label="API Configuration" />
          <Tab label="Security" />
          <Tab label="Notification Preferences" />
        </Tabs>
        
        <Box sx={{ p: 3 }}>
          {activeTab === 0 && (
            <Box>
              <ProfileSettings />
            </Box>
          )}
          
          {activeTab === 1 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                API Configuration Tab
              </Typography>
              <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
                Configure your API credentials for Alpaca and Polygon APIs. 
                These credentials are used to connect to the Alpaca API for paper trading and live trading and for getting backtest data from Polygon.
              </Typography>
              <ApiConfigForm />
            </Box>
          )}
          
          {activeTab === 2 && (
            <Box>
              <SecuritySettingsForm />
            </Box>
          )}
          
          {activeTab === 3 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Notification Preferences
              </Typography>
              <Typography variant="body1" color="text.secondary">
                Configure how and when you receive notifications.
              </Typography>
              {/* Notification preferences form would go here */}
            </Box>
          )}
        </Box>
      </Paper>
    </Box>
  );
};

export default AccountSettings;