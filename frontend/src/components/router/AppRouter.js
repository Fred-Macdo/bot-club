// src/components/router/AppRouter.js (updated to include the new routes)
import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import PrivateRoute from '../auth/PrivateRoute';
import AuthenticatedLayout from '../layout/AuthenticatedLayout';
import LoginPage from '../auth/LoginPage';
import RegisterPage from '../auth/RegisterPage';
import Dashboard from '../dashboard/Dashboard';
import StrategyBuilderPage from '../strategy/StrategyBuilder';
import Backtest from '../backtest/Backtest';
import PaperTradingPage from '../trading/PaperTrade';
import LiveTradingPage from '../trading/LiveTrade';
import AccountSettings from '../account/AccountSettings';
import LandingPage from '../landing/LandingPage';
import GettingStarted from '../docs/GettingStarted';
import ApiTest from '../ApiTest'; // Import the test component

const AppRouter = () => {
  return (
    <Routes>
      {/* Public Routes */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/api-test" element={<ApiTest />} />

      {/* Protected Routes */}
      <Route element={<PrivateRoute />}>
        <Route element={<AuthenticatedLayout />}>
          <Route path="/getting-started" element={<GettingStarted />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/strategy-builder" element={<StrategyBuilderPage />} />
          <Route path="/strategy-builder/:id" element={<StrategyBuilderPage />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/backtest/:id" element={<Backtest />} />
          <Route path="/paper-trading" element={<PaperTradingPage />} />
          <Route path="/paper-trading/:id" element={<PaperTradingPage />} />
          <Route path="/live-trading" element={<LiveTradingPage />} />
          <Route path="/live-trading/:id" element={<LiveTradingPage />} />
          <Route path="/account" element={<AccountSettings />} />
        </Route>
      </Route>

      {/* Redirect to dashboard if authenticated, login if not */}
      <Route path="*" element={<Navigate to="/dashboard" />} />
    </Routes>
  );
};

export default AppRouter;