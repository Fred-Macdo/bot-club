import React from 'react';
import { 
  Box, 
  Drawer, 
  List, 
  ListItem, 
  ListItemIcon, 
  ListItemText, 
  Typography, 
  Divider,
  useTheme
} from '@mui/material';
import { 
  Dashboard as DashboardIcon,
  Settings as SettingsIcon,
  Science as ScienceIcon,
  ShowChart as ShowChartIcon,
  Bolt as LiveIcon,
  AccountCircle as AccountIcon,
  Logout as LogoutIcon,
  MenuBook as GettingStartedIcon
} from '@mui/icons-material';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../router/AuthContext';
import logo from '../../assets/images/bot-logo.png';
import GettingStarted from '../docs/GettingStarted';

const drawerWidth = 240;

const Sidebar = () => {
  const theme = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const { signOut } = useAuth();
  const menuItems = [
    { label: 'Getting Started', icon: <GettingStartedIcon />, path: '/getting-started' },
    { label: 'Dashboard', icon: <DashboardIcon />, path: '/dashboard' },
    { label: 'Strategy Center', icon: <SettingsIcon />, path: '/strategy-builder' },
    { label: 'Backtest', icon: <ScienceIcon />, path: '/backtest' },
    { label: 'Paper Trading', icon: <ShowChartIcon />, path: '/paper-trading' },
    { label: 'Live Trading', icon: <LiveIcon />, path: '/live-trading' },
    { label: 'Account', icon: <AccountIcon />, path: '/account' },
  ];

  const isActive = (path) => {
    return location.pathname === path || location.pathname.startsWith(`${path}/`);
  };

  const handleLogout = () => {
    try {
      signOut(); // signOut is not async, so don't await it
      navigate('/login');
    } catch (error) {
      console.error('Error signing out:', error);
      // Still navigate to login even if there's an error
      navigate('/login');
    }
  };

  return (
    <Drawer
      sx={{
        width: drawerWidth,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: drawerWidth,
          boxSizing: 'border-box',
          bgcolor: theme.palette.primary.main,
          color: theme.palette.secondary.main,
        },
      }}
      variant="permanent"
      anchor="left"
    >
      {/* Logo and Title */}
      <Box 
        sx={{ 
          p: 2, 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          cursor: 'pointer'
        }}
        onClick={() => navigate('/dashboard')}
      >
        <Box component="img" src={logo} alt="Bot Club" sx={{ height: 50, mr: 1 }} />
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          BOT CLUB
        </Typography>
      </Box>
      
      <Divider sx={{ bgcolor: 'rgba(245, 237, 216, 0.2)' }} />
      
      {/* Menu Items */}
      <List sx={{ pt: 2 }}>
        {menuItems.map((item) => (
          <ListItem 
            key={item.label} 
            component={Link} 
            to={item.path}
            sx={{ 
              color: isActive(item.path) ? theme.palette.accent.main : theme.palette.secondary.main,
              bgcolor: isActive(item.path) ? 'rgba(212, 200, 146, 0.1)' : 'transparent',
              borderRight: isActive(item.path) ? `3px solid ${theme.palette.accent.main}` : 'none',
              '&:hover': {
                bgcolor: 'rgba(212, 200, 146, 0.05)',
                color: theme.palette.accent.main
              },
              mb: 1,
              borderRadius: '4px 0 0 4px'
            }}
          >
            <ListItemIcon sx={{ 
              color: isActive(item.path) ? theme.palette.accent.main : theme.palette.secondary.main,
              minWidth: 40
            }}>
              {item.icon}
            </ListItemIcon>
            <ListItemText primary={item.label} />
          </ListItem>
        ))}
      </List>
      
      <Box sx={{ flexGrow: 1 }} />
      
      {/* Logout Button */}
      <List sx={{ pb: 2 }}>
        <Divider sx={{ bgcolor: 'rgba(245, 237, 216, 0.2)', mb: 1 }} />
        <ListItem 
          button 
          onClick={handleLogout}
          sx={{
            color: theme.palette.secondary.main,
            '&:hover': {
              bgcolor: 'rgba(212, 200, 146, 0.05)',
              color: theme.palette.accent.main
            },
          }}
        >
          <ListItemIcon sx={{ color: 'inherit', minWidth: 40 }}>
            <LogoutIcon />
          </ListItemIcon>
          <ListItemText primary="Logout" />
        </ListItem>
      </List>
    </Drawer>
  );
};

export default Sidebar;