import React, { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ExecutiveOverview } from './pages/ExecutiveOverview'
import { HoldingsTable } from './pages/HoldingsTable'
import { BrokerSync } from './pages/BrokerSync'
import { Login } from './pages/Login'
import { getToken, getStoredUser, verifySession } from './utils/api'
import type { User } from './types'

export const App: React.FC = () => {
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
    <BrowserRouter>
      <Layout onLogout={handleLogout}>
        <Routes>
          <Route path="/" element={<ExecutiveOverview />} />
          <Route path="/holdings" element={<HoldingsTable />} />
          <Route path="/brokers" element={<BrokerSync />} />
          <Route path="/sync" element={<Navigate to="/brokers" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

export default App
