import { useCallback, useState } from 'react'
import { ApiError } from '../../utils/api'

export interface AnalysisRequestState<T> {
  data: T | null
  loading: boolean
  error: string | null
  authUrl: string | null
  run: (request: () => Promise<T>) => Promise<void>
}

// Runs a Kite-backed analytics request, surfacing the KITE_AUTH_REQUIRED login link separately
export function useAnalysisRequest<T>(): AnalysisRequestState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [authUrl, setAuthUrl] = useState<string | null>(null)

  const run = useCallback(async (request: () => Promise<T>) => {
    setLoading(true)
    setError(null)
    setAuthUrl(null)
    try {
      setData(await request())
    } catch (err) {
      setData(null)
      if (err instanceof ApiError) {
        const detail = err.detail as any
        if (detail && typeof detail === 'object' && detail.code === 'KITE_AUTH_REQUIRED') {
          setAuthUrl(detail.auth_url || null)
          setError(detail.message)
        } else {
          setError(typeof detail === 'string' ? detail : err.message)
        }
      } else {
        setError(err instanceof Error ? err.message : 'Unexpected error running the analysis.')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, loading, error, authUrl, run }
}
