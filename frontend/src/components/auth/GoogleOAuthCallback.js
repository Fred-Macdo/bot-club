import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../router/AuthContext';
import { 
  Box, 
  CircularProgress, 
  Typography, 
  Alert, 
  Container, 
  Paper,
  useTheme 
} from '@mui/material';
import apiClient, { authApi } from '../../api/Client';

const GoogleOAuthCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const theme = useTheme();
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Processing...');

  useEffect(() => {
    const handleOAuthCallback = async () => {
      try {
        // Get the authorization code and state from URL
        const code = searchParams.get('code');
        const state = searchParams.get('state');
        const errorParam = searchParams.get('error');

        // Check for OAuth errors
        if (errorParam) {
          setError(`Authentication failed: ${errorParam}`);
          setTimeout(() => navigate('/login'), 3000);
          return;
        }

        // Verify state to prevent CSRF attacks
        const savedState = sessionStorage.getItem('oauth_state');
        if (state !== savedState) {
          setError('Invalid state parameter. Please try again.');
          setTimeout(() => navigate('/login'), 3000);
          return;
        }

        // Clear saved state
        sessionStorage.removeItem('oauth_state');

        if (!code) {
          setError('No authorization code received');
          setTimeout(() => navigate('/login'), 3000);
          return;
        }

        setStatus('Exchanging code for token...');

        // Exchange code for token with backend
        const backendUrl = process.env.REACT_APP_API_URL || '';
        const response = await fetch(`${backendUrl}/api/auth/google/callback?code=${code}`, {
          method: 'GET',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to authenticate with Google');
        }

        const data = await response.json();
        
        // Store the access token in memory (httpOnly cookie is set by the backend)
        if (data.access_token) {
          apiClient.setToken(data.access_token);
          
          setStatus('Fetching user profile...');
          
          // Fetch user profile
          const userProfile = await authApi.getUserProfile();
          setUser(userProfile);
          
          setStatus('Success! Redirecting...');
          
          // Redirect to dashboard
          setTimeout(() => navigate('/dashboard'), 1000);
        } else {
          throw new Error('No access token received');
        }
      } catch (error) {
        console.error('OAuth callback error:', error);
        setError(error.message || 'Authentication failed');
        setTimeout(() => navigate('/login'), 3000);
      }
    };

    handleOAuthCallback();
  }, [searchParams, navigate, setUser]);

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
        {error ? (
          <>
            <Alert severity="error" sx={{ width: '100%', mb: 2 }}>
              {error}
            </Alert>
            <Typography sx={{ 
              color: theme.palette.mode === 'light' 
                ? theme.palette.secondary.main 
                : theme.palette.text.primary,
              textAlign: 'center' 
            }}>
              Redirecting to login page...
            </Typography>
          </>
        ) : (
          <>
            <CircularProgress 
              sx={{ 
                color: theme.palette.mode === 'light' 
                  ? theme.palette.secondary.main 
                  : theme.palette.primary.main,
                mb: 3 
              }} 
              size={60} 
            />
            <Typography 
              variant="h6" 
              sx={{ 
                color: theme.palette.mode === 'light' 
                  ? theme.palette.secondary.main 
                  : theme.palette.text.primary,
                textAlign: 'center', 
                mb: 1 
              }}
            >
              Completing Sign In
            </Typography>
            <Typography sx={{ 
              color: theme.palette.mode === 'light' 
                ? theme.palette.secondary.main 
                : theme.palette.text.secondary,
              textAlign: 'center', 
              opacity: 0.8 
            }}>
              {status}
            </Typography>
          </>
        )}
      </Paper>
    </Container>
  );
};

export default GoogleOAuthCallback;