import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

const OverviewPage = lazy(() => import('./pages/Overview').then((module) => ({ default: module.OverviewPage })));
const InvestorPage = lazy(() => import('./pages/Investor').then((module) => ({ default: module.InvestorPage })));
const FinancialsPage = lazy(() => import('./pages/Financials').then((module) => ({ default: module.FinancialsPage })));
const AIPage = lazy(() => import('./pages/AI').then((module) => ({ default: module.AIPage })));
const DecisionPage = lazy(() => import('./pages/Decision').then((module) => ({ default: module.DecisionPage })));
const MethodologyPage = lazy(() => import('./pages/Methodology').then((module) => ({ default: module.MethodologyPage })));
const DevKitPage = lazy(() => import('./pages/DevKit').then((module) => ({ default: module.DevKitPage })));

export const App: React.FC = () => {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Suspense fallback={<div className="route-loading" role="status" aria-live="polite">Đang tải…</div>}>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/investor" element={<InvestorPage />} />
          <Route path="/financials" element={<FinancialsPage />} />
          <Route path="/ai" element={<AIPage />} />
          <Route path="/decision" element={<DecisionPage />} />
          <Route path="/methodology" element={<MethodologyPage />} />
          <Route path="/__kit" element={<DevKitPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};
