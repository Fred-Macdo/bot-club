// src/context/AlpacaContext.js
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useAuth } from '../components/router/AuthContext';
import { userConfigApi } from '../api/Client';

const AlpacaContext = createContext();

export function AlpacaProvider({ children }) {
  const { user } = useAuth();

  const [paperConfig, setPaperConfig] = useState(null);
  const [liveConfig, setLiveConfig] = useState(null);
  const [polygonConfig, setPolygonConfig] = useState(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchConfig = useCallback(async () => {
    if (!user) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await userConfigApi.getConfig();
      
      if (response) {
        const {
          alpaca_paper_api_key,
          alpaca_paper_secret_key,
          alpaca_paper_endpoint,
          alpaca_live_api_key,
          alpaca_live_secret_key,
          alpaca_live_endpoint,
          polygon_api_key_name,
          polygon_secret_key
        } = response;

        if (alpaca_paper_api_key) {
          setPaperConfig({
            key: alpaca_paper_api_key,
            secret: alpaca_paper_secret_key || '',
            endpoint: alpaca_paper_endpoint || 'https://paper-api.alpaca.markets'
          });
        } else {
          setPaperConfig(null);
        }

        if (alpaca_live_api_key) {
          setLiveConfig({
            key: alpaca_live_api_key,
            secret: alpaca_live_secret_key || '',
            endpoint: alpaca_live_endpoint || 'https://api.alpaca.markets'
          });
        } else {
          setLiveConfig(null);
        }

        if (polygon_api_key_name) {
          setPolygonConfig({
            name: polygon_api_key_name,
            key: polygon_secret_key || ''
          });
        } else {
          setPolygonConfig(null);
        }
      }
    } catch (err) {
      console.error('Failed to fetch API configurations:', err);
      setError(err.message || 'Could not load API configurations.');
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const saveAlpacaConfig = async (configData) => {
    try {
      await userConfigApi.saveAlpacaConfig(configData);
      // Refetch config after saving to update the context state
      await fetchConfig(); 
      return { success: true };
    } catch (error) {
      console.error('Error saving Alpaca config via context:', error);
      return { success: false, error: error.message };
    }
  };

  const savePolygonConfig = async (configData) => {
    try {
      await userConfigApi.savePolygonConfig(configData);
      await fetchConfig();
      return { success: true };
    } catch (error) {
      console.error('Error saving Polygon config via context:', error);
      return { success: false, error: error.message };
    }
  };

  const value = {
    paperConfig,
    liveConfig,
    polygonConfig,
    loading,
    error,
    isAlpacaConfigured: !!(paperConfig || liveConfig),
    isPolygonConfigured: !!polygonConfig,
    refetchConfig: fetchConfig,
    saveAlpacaConfig,
    savePolygonConfig
  };

  return <AlpacaContext.Provider value={value}>{children}</AlpacaContext.Provider>;
}

export function useAlpaca() {
  return useContext(AlpacaContext);
}