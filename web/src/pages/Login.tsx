import React, { useEffect, useState, useRef } from 'react'
import { Shield, AlertCircle, Lock } from 'lucide-react'
import {
  authenticateWithGoogle,
  fetchAuthConfig,
} from '../utils/api'
import type { User } from '../types'

declare global {
  interface Window {
    google?: any
  }
}

interface LoginProps {
  onLoginSuccess: (user: User) => void
}

export const Login: React.FC<LoginProps> = ({ onLoginSuccess }) => {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [clientId, setClientId] = useState<string>('')
  const googleBtnRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // 1. Fetch Google Client ID from backend
    fetchAuthConfig()
      .then((cfg) => {
        if (cfg.google_client_id) {
          setClientId(cfg.google_client_id)
        }
      })
      .catch((err) => {
        console.warn('Could not load auth configuration:', err)
      })
  }, [])

  useEffect(() => {
    if (!clientId) return

    // 2. Initialize Google Identity Services
    const initGoogle = () => {
      if (window.google?.accounts?.id && googleBtnRef.current) {
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: async (response: any) => {
            if (!response.credential) return
            setLoading(true)
            setError(null)
            try {
              const authRes = await authenticateWithGoogle(response.credential)
              onLoginSuccess(authRes.user)
            } catch (err: any) {
              console.error('Google verification failed:', err)
              setError('Google verification failed. Please try again.')
            } finally {
              setLoading(false)
            }
          },
        })

        // Render official Google button
        googleBtnRef.current.innerHTML = ''
        window.google.accounts.id.renderButton(googleBtnRef.current, {
          theme: 'outline',
          size: 'large',
          width: 320,
          text: 'continue_with',
          shape: 'rectangular',
        })

        // Prompt Google One Tap
        try {
          window.google.accounts.id.prompt()
        } catch {
          // Ignore one-tap prompt rejection
        }
      }
    }

    // Run when google script is loaded or poll briefly
    if (window.google?.accounts?.id) {
      initGoogle()
    } else {
      const interval = setInterval(() => {
        if (window.google?.accounts?.id) {
          clearInterval(interval)
          initGoogle()
        }
      }, 300)
      return () => clearInterval(interval)
    }
  }, [clientId, onLoginSuccess])

  return (
    <div className="min-h-screen bg-surface flex flex-col justify-center items-center px-4 font-sans antialiased">
      <div className="w-full max-w-md bg-surface-container-lowest p-8 rounded-2xl shadow-xl border border-outline-variant/30 flex flex-col items-center text-center">
        {/* Brand Icon */}
        <div className="w-14 h-14 rounded-xl bg-primary flex items-center justify-center text-on-primary shadow-md mb-4">
          <Shield className="w-8 h-8" />
        </div>

        {/* Title & Badge */}
        <div className="flex items-center gap-1.5 text-xs text-on-surface-variant font-semibold uppercase tracking-wider mb-1">
          <Lock className="w-3.5 h-3.5 text-on-tertiary-container" />
          <span>Sovereign Family Trust</span>
        </div>
        <h1 className="font-serif text-3xl text-primary font-normal tracking-tight">
          WealthVault
        </h1>
        <p className="text-sm text-secondary mt-2 mb-6 leading-relaxed">
          Executive Portfolio Intelligence &amp; Multi-Broker Telemetry. Sign in with your authorized Google account to access your private wealth ledger.
        </p>

        {error && (
          <div className="w-full bg-error-container/40 border border-error/20 p-3 rounded-lg flex items-center gap-2 text-xs text-on-error-container mb-4 text-left">
            <AlertCircle className="w-4 h-4 text-error shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Google Sign-In Container */}
        <div className="w-full flex flex-col items-center justify-center min-h-[50px] my-2">
          <div ref={googleBtnRef} id="google-signin-btn" className="flex justify-center w-full"></div>
          {loading && (
            <div className="flex items-center gap-2 text-xs text-secondary mt-3">
              <div className="w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
              <span>Securing sovereign session...</span>
            </div>
          )}
        </div>

        <p className="text-[11px] text-outline mt-8 leading-normal border-t border-surface-container pt-4 w-full">
          Multi-tenant partitioned via Azure Tables. Verified with Zerodha Kite, Coin, and INDmoney API feeds.
        </p>
      </div>
    </div>
  )
}
