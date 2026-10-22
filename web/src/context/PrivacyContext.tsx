import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'

const STORAGE_KEY = 'wv_hide_amounts'

// amounts start hidden; they show only once someone has switched them on with the eye button
const readInitial = (): boolean => {
  try {
    return localStorage.getItem(STORAGE_KEY) !== 'false'
  } catch {
    return true
  }
}

interface PrivacyContextValue {
  hidden: boolean
  toggle: () => void
}

const PrivacyContext = createContext<PrivacyContextValue>({ hidden: true, toggle: () => {} })

export const PrivacyProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [hidden, setHidden] = useState<boolean>(readInitial)

  const toggle = useCallback(() => {
    setHidden((h) => {
      const next = !h
      try {
        localStorage.setItem(STORAGE_KEY, String(next))
      } catch {
        // storage unavailable: the choice just will not persist
      }
      return next
    })
  }, [])

  const value = useMemo(() => ({ hidden, toggle }), [hidden, toggle])
  return <PrivacyContext.Provider value={value}>{children}</PrivacyContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const usePrivacy = () => useContext(PrivacyContext)
