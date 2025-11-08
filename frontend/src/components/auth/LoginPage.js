// 6. Update LoginPage.js with the correct auth hook
// /frontend/src/components/auth/LoginPage.js
import React, { useState, useEffect } from 'react';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import { useAuth } from '../router/AuthContext'; // Updated path
import {
  Box, Button, TextField, Typography, Paper, Container, Alert, CircularProgress, Link, Divider, useTheme
} from '@mui/material';
import GoogleOAuthButton from './GoogleOAuthButton';

const LoginPage = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [formError, setFormError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { signIn, user } = useAuth(); // Use the auth hook and get user state
  const theme = useTheme();

  // If already logged in, redirect to dashboard
  useEffect(() => {
    if (user) {
      console.log('User already logged in, redirecting to dashboard');
      navigate('/dashboard');
    }
  }, [user, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormError('');
    setLoading(true);

    console.log('Attempting to sign in with:', { username });

    try {
      const { data, error } = await signIn(username, password);
      
      if (error) {
        setFormError(error.message);
        console.error('Login error:', error);
      } else {
        console.log('Login successful:', data);
        navigate('/dashboard');
      }
    } catch (error) {
      setFormError(error.message || 'Login failed');
      console.error('Login error:', error);
    } finally {
      setLoading(false);
    }
  };

  // For testing/demo purposes - auto-fill credentials
  const fillDemoCredentials = () => {
    setUsername('demo@botclub.com');
    setPassword('demo123');
  };

  return (
    <Container
      component="main"
      maxWidth="xs"
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: theme.palette.background.default,
      }}
    >
      <Paper
        elevation={3}
        sx={{
          padding: 4,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          backgroundColor: theme.palette.mode === 'light' 
            ? theme.palette.primary.main 
            : theme.palette.background.paper,
          color: theme.palette.mode === 'light' 
            ? theme.palette.secondary.main 
            : theme.palette.text.primary,
          width: '100%',
          maxWidth: '400px',
        }}
      >
        <Typography 
          component="h1" 
          variant="h5" 
          sx={{ 
            color: theme.palette.mode === 'light' 
              ? theme.palette.secondary.main 
              : theme.palette.text.primary,
            fontWeight: 700, 
            mb: 3 
          }}
        >
          Login
        </Typography>
        
        {formError && (
          <Alert severity="error" sx={{ mt: 2, width: '100%', mb: 2 }}>
            {formError}
          </Alert>
        )}

        {/* Google OAuth Button */}
        <Box sx={{ width: '100%', mb: 2 }}>
          <GoogleOAuthButton
            onError={(error) => setFormError(error.message)}
            disabled={loading}
          />
        </Box>

        {/* Divider */}
        <Box sx={{ width: '100%', display: 'flex', alignItems: 'center', my: 2 }}>
          <Divider sx={{ flex: 1 }} />
          <Typography sx={{ 
            px: 2, 
            color: theme.palette.mode === 'light' 
              ? theme.palette.secondary.main 
              : theme.palette.text.secondary,
            opacity: 0.7, 
            fontSize: '0.875rem' 
          }}>
            OR
          </Typography>
          <Divider sx={{ flex: 1 }} />
        </Box>

        <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1, width: '100%' }}>
          <Typography sx={{ 
            color: theme.palette.mode === 'light' 
              ? theme.palette.secondary.main 
              : theme.palette.text.primary,
            mb: 1 
          }}>
            Username *
          </Typography>
          <TextField
            required
            fullWidth
            id="username"
            name="username"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
            variant="outlined"
            InputProps={{
              sx: {
                backgroundColor: theme.palette.mode === 'light' 
                  ? '#f5edd8' 
                  : theme.palette.background.default,
                color: theme.palette.mode === 'light' 
                  ? theme.palette.primary.main 
                  : theme.palette.text.primary,
                '& .MuiOutlinedInput-notchedOutline': {
                  borderColor: 'transparent',
                },
              }
            }}
            sx={{ mb: 3 }}
          />
          
          <Typography sx={{ 
            color: theme.palette.mode === 'light' 
              ? theme.palette.secondary.main 
              : theme.palette.text.primary,
            mb: 1 
          }}>
            Password *
          </Typography>
          <TextField
            required
            fullWidth
            name="password"
            type="password"
            id="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            variant="outlined"
            InputProps={{
              sx: {
                backgroundColor: theme.palette.mode === 'light' 
                  ? '#f5edd8' 
                  : theme.palette.background.default,
                color: theme.palette.mode === 'light' 
                  ? theme.palette.primary.main 
                  : theme.palette.text.primary,
                '& .MuiOutlinedInput-notchedOutline': {
                  borderColor: 'transparent',
                },
              }
            }}
            sx={{ mb: 3 }}
          />
          
          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{
              mt: 1, 
              mb: 2,
              py: 1.5,
              backgroundColor: theme.palette.secondary.main,
              color: theme.palette.primary.main,
              fontWeight: 700,
              '&:hover': { 
                backgroundColor: theme.palette.mode === 'light' ? '#bfae6a' : '#f0e4b4'
              },
              textTransform: 'uppercase'
            }}
            disabled={loading}
          >
            {loading ? <CircularProgress size={24} /> : 'LOGIN'}
          </Button>
          
          {/* Added demo button for easy testing */}
          <Button
            fullWidth
            variant="outlined"
            onClick={fillDemoCredentials}
            sx={{
              mb: 2,
              borderColor: theme.palette.secondary.main,
              color: theme.palette.secondary.main,
              '&:hover': {
                borderColor: theme.palette.mode === 'light' ? '#f5edd8' : '#e5d9a3',
                backgroundColor: theme.palette.mode === 'light' 
                  ? 'rgba(245, 237, 216, 0.1)' 
                  : 'rgba(229, 217, 163, 0.1)',
              }
            }}
            disabled={loading}
          >
            Use Demo Account
          </Button>
          
          <Box sx={{ mt: 2, display: 'flex', justifyContent: 'center' }}>
            <Link 
              component={RouterLink} 
              to="/register" 
              variant="body2" 
              sx={{ color: theme.palette.secondary.main }}
            >
              {"Don't have an account? Register"}
            </Link>
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default LoginPage;