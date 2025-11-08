import React, { useState, useMemo } from 'react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { BrowserRouter } from 'react-router-dom';
import AppRouter from './components/router/AppRouter';
import { StrategyProvider } from './context/StrategyContext';
import { AuthProvider } from './components/router/AuthContext';
import { AlpacaProvider } from './context/AlpacaContext';
import { DeployedStrategyProvider } from './context/DeployedStrategyContext';
import { Box } from '@mui/material';
import ThemeToggle from './components/common/ThemeToggle';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';

function App() {
  const [mode, setMode] = useState(() => {
    const savedMode = localStorage.getItem('theme-mode');
    return savedMode === 'dark' ? 'dark' : 'light';
  });

  const toggleColorMode = () => {
    setMode((prevMode) => {
      const newMode = prevMode === 'light' ? 'dark' : 'light';
      localStorage.setItem('theme-mode', newMode);
      return newMode;
    });
  };

  // Create theme based on current mode
  const theme = useMemo(() => createTheme({
    palette: {
      mode,
      primary: {
        main: '#07372a', // Keep BotClub dark green (works in both themes)
      },
      secondary: {
        // Adjust gold slightly for better contrast in dark mode
        main: mode === 'light' ? '#d4c892' : '#e5d9a3',
      },
      accent: {
        // Adjust accent slightly for better contrast in dark mode
        main: mode === 'light' ? '#d4c892' : '#e5d9a3',
      },
      background: {
        // Change background based on mode
        default: mode === 'light' ? '#f5edd8' : '#121212',
        paper: mode === 'light' ? '#ffffff' : '#1e1e1e',
      },
      text: {
        // Set text colors for dark mode
        primary: mode === 'light' ? 'rgba(0, 0, 0, 0.87)' : '#ffffff',
        secondary: mode === 'light' ? 'rgba(0, 0, 0, 0.6)' : 'rgba(255, 255, 255, 0.7)',
      },
    },
    typography: {
      fontFamily: [
        'Roboto',
        '-apple-system',
        'BlinkMacSystemFont',
        '"Segoe UI"',
        '"Helvetica Neue"',
        'Arial',
        'sans-serif',
        '"Apple Color Emoji"',
        '"Segoe UI Emoji"',
        '"Segoe UI Symbol"',
      ].join(','),
    },
    components: {
      // Adjust components based on theme
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundColor: mode === 'light' ? '#ffffff' : '#1e1e1e',
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            backgroundColor: mode === 'light' ? '#ffffff' : '#1e1e1e',
          },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundColor: mode === 'light' ? '#07372a' : '#121212',
          },
        },
      },
      MuiDrawer: {
        styleOverrides: {
          paper: {
            backgroundColor: mode === 'light' ? '#ffffff' : '#1e1e1e',
          },
        },
      },
      MuiDivider: {
        styleOverrides: {
          root: {
            borderColor: mode === 'light' ? 'rgba(0, 0, 0, 0.12)' : 'rgba(255, 255, 255, 0.12)',
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            // Ensure buttons have enough contrast in dark mode
            color: mode === 'dark' && 'white',
          },
        },
      },
    },
  }), [mode]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {/* Theme toggle button - you can move this to your navbar/header component */}
      <Box sx={{ position: 'fixed', top: 20, right: 20, zIndex: 2000 }}>
        <ThemeToggle toggleColorMode={toggleColorMode} />
      </Box>

      <AuthProvider>
        <StrategyProvider>
          <AlpacaProvider>
            <DeployedStrategyProvider>
              <BrowserRouter>
                <AppRouter />
              </BrowserRouter>
            </DeployedStrategyProvider>
          </AlpacaProvider>
        </StrategyProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;