import React, { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { PortfolioProvider } from './context/PortfolioContext'
import { ThemeProvider } from './context/ThemeContext'
import { PrivacyProvider } from './context/PrivacyContext'
import { ExecutiveOverview } from './pages/ExecutiveOverview'
import { Signals } from './pages/Signals'
import { HoldingsTable } from './pages/HoldingsTable'
import { BrokerSync } from './pages/BrokerSync'
import { MomentumAnalyzer } from './pages/MomentumAnalyzer'
import { AthStrategy } from './pages/AthStrategy'
import { Login } from './pages/Login'
import { Account } from './pages/Account'
import { DeleteAccountInfo, PrivacyPolicy } from './pages/Legal'
import { getToken, getStoredUser, verifySession } from './utils/api'
import { identify } from './utils/analytics'
import type { User } from './types'

const SignedInApp: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<User | null>(getStoredUser())
  const [isVerifying, setIsVerifying] = useState(true)

  useEffect(() => {
    // Check if token exists and verify validity against the backend
    const token = getToken()
    if (!token) {
      setCurrentUser(null)
      setIsVerifying(false)
      return
    }

    verifySession()
      .then((user) => {
        setCurrentUser(user)
      })
      .catch(() => {
        setCurrentUser(null)
      })
      .finally(() => {
        setIsVerifying(false)
      })
  }, [])

  useEffect(() => {
    void identify(currentUser?.user_id)
  }, [currentUser?.user_id])

  const handleLoginSuccess = (user: User) => {
    setCurrentUser(user)
  }

  const handleLogout = () => {
    setCurrentUser(null)
  }

  // Loading spinner during initial session verification
  if (isVerifying) {
    return (
      <div className="min-h-screen bg-surface flex flex-col items-center justify-center font-sans">
        <div className="w-10 h-10 border-3 border-primary border-t-transparent rounded-full animate-spin"></div>
        <p className="mt-4 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
          Validating Sovereign Session...
        </p>
      </div>
    )
  }

  // If unauthenticated, show Google Sign-In Page
  if (!currentUser) {
    return <Login onLoginSuccess={handleLoginSuccess} />
  }

  // If authenticated, render full WealthVault Dashboard
  return (
    <ThemeProvider>
    <PrivacyProvider>
    <BrowserRouter>
      <PortfolioProvider>
        <Layout onLogout={handleLogout}>
          <Routes>
            <Route path="/" element={<ExecutiveOverview />} />
            <Route path="/holdings" element={<HoldingsTable />} />
            <Route path="/stage2" element={<Navigate to="/signals?source=stage2" replace />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/momentum" element={<MomentumAnalyzer />} />
            <Route path="/strategy" element={<AthStrategy />} />
            <Route path="/brokers" element={<BrokerSync />} />
            <Route path="/account" element={<Account />} />
            <Route path="/sync" element={<Navigate to="/brokers" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Layout>
      </PortfolioProvider>
    </BrowserRouter>
    </PrivacyProvider>
    </ThemeProvider>
  )
}

export const App: React.FC = () => {
  // Public pages Google Play links to; they work without signing in
  const publicPath = window.location.pathname.replace(/\/+$/, '')
  if (publicPath === '/privacy') return <PrivacyPolicy />
  if (publicPath === '/delete-account') return <DeleteAccountInfo />
  return <SignedInApp />
}

export default App
