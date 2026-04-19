// frontend/src/context/StrategyContext.js
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useAuth } from '../components/router/AuthContext';
import apiClient from '../api/Client'; // Corrected import path

const StrategyContext = createContext();

export const useStrategy = () => {
  const context = useContext(StrategyContext);
  if (!context) {
    throw new Error('useStrategy must be used within a StrategyProvider');
  }
  return context;
};

export const StrategyProvider = ({ children }) => {
  const { user } = useAuth();
  const [strategies, setStrategies] = useState([]);
  const [defaultStrategies, setDefaultStrategies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);

  // Fetch user strategies
  const fetchUserStrategies = useCallback(async () => {
    if (!user) {
      console.log('No user found, skipping strategy fetch');
      setStrategies([]);
      return;
    }
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch('/api/strategy/user_strategies', {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        // Try to parse error message from response
        let errorMessage = `Failed to fetch strategies: ${response.statusText}`;
        try {
            const errorData = await response.json();
            errorMessage = errorData.detail || errorMessage;
        } catch (e) {
            // Ignore if response is not JSON
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      console.log('Fetched user strategies:', data);
      
      // Ensure strategies is always an array and normalize ID
      const normalizedStrategies = (Array.isArray(data) ? data : []).map(strategy => ({
        ...strategy,
        id: strategy.id || strategy._id
      }));

      setStrategies(normalizedStrategies);
      setLastRefresh(new Date());
    } catch (err) {
      console.error('Error fetching strategies:', err);
      setError(err.message);
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  }, [user]); // Keep user dependency, as fetch should run if user logs in/out

  // Fetch default strategies (public endpoint)
  const fetchDefaultStrategies = useCallback(async () => {
    try {
      const response = await fetch('/api/strategy/default');
      
      if (!response.ok) {
        throw new Error(`Failed to fetch default strategies: ${response.statusText}`);
      }

      const data = await response.json();
      console.log('Fetched default strategies:', data);
      
      setDefaultStrategies(data);
    } catch (err) {
      console.error('Error fetching default strategies:', err);
      // Don't set error for default strategies as it's not critical
    }
  }, []);

  // Save a new strategy
  const saveStrategy = useCallback(async (strategyData) => {
    if (!user) {
      throw new Error('User must be authenticated to save strategies');
    }
    try {
      setLoading(true);
      setError(null);
      const response = await fetch('/api/strategy', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(strategyData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save strategy');
      }

      const savedStrategy = await response.json();
      console.log('Strategy saved successfully:', savedStrategy);

      // IMPORTANT: Refresh the strategies list after successful save
      await fetchUserStrategies();
      
      return { success: true, strategy: savedStrategy };
    } catch (err) {
      console.error('Error saving strategy:', err);
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setLoading(false);
    }
  }, [user, fetchUserStrategies]);
  // Update an existing strategy
  const updateStrategy = useCallback(async (strategyId, strategyData) => {
    if (!user) {
      throw new Error('User must be authenticated to update strategies');
    }
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`/api/strategy/${strategyId}`, {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(strategyData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update strategy');
      }

      const updatedStrategy = await response.json();
      console.log('Strategy updated successfully:', updatedStrategy);

      // Refresh strategies list
      await fetchUserStrategies();
      
      return { success: true, strategy: updatedStrategy };
    } catch (err) {
      console.error('Error updating strategy:', err);
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setLoading(false);
    }
  }, [user, fetchUserStrategies]);
  // Delete a strategy
  const deleteStrategy = useCallback(async (strategyId) => {
    if (!user) {
      throw new Error('User must be authenticated to delete strategies');
    }
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`/api/strategy/${strategyId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete strategy');
      }

      console.log('Strategy deleted successfully');

      // Refresh strategies list
      await fetchUserStrategies();
      
      return { success: true };
    } catch (err) {
      console.error('Error deleting strategy:', err);
      setError(err.message);
      return { success: false, error: err.message };
    } finally {
      setLoading(false);
    }
  }, [user, fetchUserStrategies]);

  // Manually refresh strategies
  const refreshStrategies = useCallback(async () => {
    console.log('Manually refreshing strategies...');
    await Promise.all([
      fetchUserStrategies(),
      fetchDefaultStrategies()
    ]);
  }, [fetchUserStrategies, fetchDefaultStrategies]);

  // Initial load and user change effect
  useEffect(() => {
    if (user) {
      console.log('User detected, fetching strategies...');
      fetchUserStrategies();
      fetchDefaultStrategies();
    } else {
      console.log('No user, clearing strategies...');
      setStrategies([]);
      // Still fetch default strategies even without user
      fetchDefaultStrategies();
    }
  }, [user, fetchUserStrategies, fetchDefaultStrategies]);

  const value = {
    strategies,
    defaultStrategies,
    loading,
    error,
    lastRefresh,
    saveStrategy,
    updateStrategy,
    deleteStrategy,
    refreshStrategies,
    // Utility functions
    getStrategyById: (id) => strategies.find(s => s.id === id),
    hasStrategies: strategies.length > 0,
    totalStrategies: strategies.length + defaultStrategies.length
  };

  return (
    <StrategyContext.Provider value={value}>
      {children}
    </StrategyContext.Provider>
  );
};

export default StrategyContext;