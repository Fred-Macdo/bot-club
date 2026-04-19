import React, { useState } from 'react';
import { Button, Box, CircularProgress, useTheme } from '@mui/material';
import GoogleIcon from '@mui/icons-material/Google';

const GoogleOAuthButton = ({ onSuccess, onError, disabled = false, fullWidth = true }) => {
  const [loading, setLoading] = useState(false);
  const theme = useTheme();

  const handleGoogleLogin = () => {
    setLoading(true);
    try {
      // Get the backend OAuth URL
      const backendUrl = process.env.REACT_APP_API_URL || '';
      const redirectUri = `${window.location.origin}/auth/google/callback`;
      
      // Construct Google OAuth URL with state for CSRF protection
      const state = Math.random().toString(36).substring(7);
      sessionStorage.setItem('oauth_state', state);
      
      // Redirect to backend's Google OAuth endpoint
      const oauthUrl = `${backendUrl}/api/auth/google/login?redirect_uri=${encodeURIComponent(redirectUri)}&state=${state}`;
      window.location.href = oauthUrl;
    } catch (error) {
      console.error('Google OAuth initialization error:', error);
      setLoading(false);
      if (onError) {
        onError(error);
      }
    }
  };

  return (
    <Button
      fullWidth={fullWidth}
      variant="outlined"
      onClick={handleGoogleLogin}
      disabled={disabled || loading}
      sx={{
        py: 1.5,
        borderColor: theme.palette.secondary.main,
        color: theme.palette.secondary.main,
        fontWeight: 600,
        textTransform: 'none',
        position: 'relative',
        '&:hover': {
          borderColor: theme.palette.mode === 'light' ? '#bfae6a' : '#f0e4b4',
          backgroundColor: theme.palette.mode === 'light' 
            ? 'rgba(245, 237, 216, 0.1)' 
            : 'rgba(229, 217, 163, 0.1)',
        },
        '&:disabled': {
          borderColor: `${theme.palette.secondary.main}50`,
          color: `${theme.palette.secondary.main}50`,
        },
      }}
    >
      {loading ? (
        <CircularProgress size={24} sx={{ color: theme.palette.secondary.main }} />
      ) : (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <GoogleIcon sx={{ fontSize: 20 }} />
          <span>Continue with Google</span>
        </Box>
      )}
    </Button>
  );
};

export default GoogleOAuthButton;