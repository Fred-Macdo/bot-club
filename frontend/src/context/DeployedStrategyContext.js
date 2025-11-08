import React, { createContext, useContext, useState, useEffect } from 'react';
import { getTradingStatus } from '../api/Client';

const DeployedStrategyContext = createContext();

export const useDeployedStrategy = () => {
  const context = useContext(DeployedStrategyContext);
  if (!context) {
    throw new Error('useDeployedStrategy must be used within a DeployedStrategyProvider');
  }
  return context;
};

export const DeployedStrategyProvider = ({ children }) => {
  const [deployedStrategy, setDeployedStrategy] = useState(null);
  const [isDeployed, setIsDeployed] = useState(false);
  const [dataProvider, setDataProvider] = useState('alpaca');
  const [deploymentTime, setDeploymentTime] = useState(null);

  // Load deployed strategy from localStorage on mount and verify with backend
  useEffect(() => {
    const verifyAndRestoreDeployment = async () => {
      try {
        const stored = localStorage.getItem('deployedStrategy');
        if (!stored) return;
        
        const data = JSON.parse(stored);
        
        // Check if deployment is still valid (less than 24 hours old)
        const now = Date.now();
        const deployedAt = data.deploymentTime || 0;
        const hoursSinceDeployment = (now - deployedAt) / (1000 * 60 * 60);
        
        if (hoursSinceDeployment >= 24) {
          localStorage.removeItem('deployedStrategy');
          console.log('Cleared old deployment (>24 hours)');
          return;
        }
        
        // Verify with backend that the strategy is actually running
        if (data.isDeployed && data.strategy?.id) {
          console.log('Verifying deployment status with backend for strategy:', data.strategy.id);
          const statusResult = await getTradingStatus(data.strategy.id);
          
          if (statusResult.success && statusResult.data.is_running) {
            // Backend confirms it's running, restore the state
            setDeployedStrategy(data.strategy);
            setIsDeployed(true);
            setDataProvider(data.dataProvider || 'alpaca');
            setDeploymentTime(data.deploymentTime);
            console.log('✅ Deployment verified and restored:', data.strategy.name);
          } else {
            // Backend says it's not running, clear localStorage
            localStorage.removeItem('deployedStrategy');
            console.log('❌ Backend reports strategy not running, cleared stale deployment');
          }
        } else {
          // Not marked as deployed, just restore the strategy reference
          setDeployedStrategy(data.strategy);
          setDataProvider(data.dataProvider || 'alpaca');
          console.log('Restored strategy reference (not deployed)');
        }
      } catch (error) {
        console.error('Error verifying/restoring deployed strategy:', error);
        // Don't clear on error - might be temporary network issue
      }
    };
    
    verifyAndRestoreDeployment();
  }, []);

  // Save to localStorage whenever state changes
  useEffect(() => {
    if (deployedStrategy && isDeployed) {
      const data = {
        strategy: deployedStrategy,
        isDeployed,
        dataProvider,
        deploymentTime: deploymentTime || Date.now()
      };
      localStorage.setItem('deployedStrategy', JSON.stringify(data));
      console.log('Saved deployed strategy to localStorage');
    } else if (!isDeployed) {
      localStorage.removeItem('deployedStrategy');
      console.log('Removed deployed strategy from localStorage');
    }
  }, [deployedStrategy, isDeployed, dataProvider, deploymentTime]);

  const deployStrategy = (strategy, provider = 'alpaca') => {
    setDeployedStrategy(strategy);
    setIsDeployed(true);
    setDataProvider(provider);
    setDeploymentTime(Date.now());
  };

  const stopStrategy = () => {
    setIsDeployed(false);
    // Don't clear deployedStrategy immediately to allow viewing final results
    // It will be cleared on next deployment or after timeout
  };

  const clearDeployment = () => {
    setDeployedStrategy(null);
    setIsDeployed(false);
    setDataProvider('alpaca');
    setDeploymentTime(null);
    localStorage.removeItem('deployedStrategy');
  };

  const value = {
    deployedStrategy,
    isDeployed,
    dataProvider,
    deploymentTime,
    deployStrategy,
    stopStrategy,
    clearDeployment,
    setDataProvider
  };

  return (
    <DeployedStrategyContext.Provider value={value}>
      {children}
    </DeployedStrategyContext.Provider>
  );
};

