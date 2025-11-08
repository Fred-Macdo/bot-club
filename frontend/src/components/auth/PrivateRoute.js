// 5. Update PrivateRoute.js to use the correct AuthContext
// /frontend/src/components/auth/PrivateRoute.js
import React, { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../router/AuthContext'; // Updated path
import { Box, CircularProgress, Typography } from '@mui/material';

const PrivateRoute = () => {
  const { user, loading } = useAuth();
  const location = useLocation();

  // Add debug logging for authentication state
  useEffect(() => {
    console.log('PrivateRoute - Auth State:', { 
      isAuthenticated: !!user, 
      isLoading: loading,
      path: location.pathname
    });
  }, [user, loading, location]);

  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          background: '#113c35',
          color: '#d4c892',
        }}
      >
        <CircularProgress size={60} sx={{ color: '#d4c892' }} />
        <Typography variant="h6" sx={{ mt: 2 }}>
          Loading...
        </Typography>
      </Box>
    );
  }

  // If not authenticated, redirect to login
  if (!user) {
    console.log('Not authenticated, redirecting to login');
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  console.log('Authentication successful, rendering protected route');
  return <Outlet />;
};

export default PrivateRoute;