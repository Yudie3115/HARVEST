import { useCallback, useEffect, useState } from 'react'
import { createSession, getHistory } from '../api'

const SESSION_KEY = 'ph_session_id'

export function useSession(token, preferredSessionId = null, { onAccessError } = {}) {
  const [sessionId, setSessionId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const startNewSession = useCallback(() => {
    setLoading(true)
    setError(null)
    if (!token) {
      setLoading(false)
      return Promise.reject(new Error('Access token required'))
    }
    return createSession('web', token)
      .then(({ session_id }) => {
        localStorage.setItem(SESSION_KEY, session_id)
        setSessionId(session_id)
        return session_id
      })
      .catch((err) => {
        setError(err.message)
        throw err
      })
      .finally(() => setLoading(false))
  }, [token])

  useEffect(() => {
    if (!token) {
      setSessionId(null)
      setLoading(false)
      return
    }
    const stored = preferredSessionId || localStorage.getItem(SESSION_KEY)
    if (!stored) {
      startNewSession().catch(() => {})
      return
    }

    getHistory(stored, token)
      .then(() => {
        setSessionId(stored)
        setLoading(false)
      })
      .catch((err) => {
        if ([401, 403].includes(err.status)) onAccessError?.(err)
        if ([401, 403, 404, 422].includes(err.status)) {
          localStorage.removeItem(SESSION_KEY)
          if (![401].includes(err.status)) startNewSession().catch(() => {})
          else setLoading(false)
          return
        }
        setSessionId(stored)
        setError(err.message)
        setLoading(false)
      })
  }, [token, preferredSessionId, startNewSession, onAccessError])

  const resetSession = useCallback(() => {
    localStorage.removeItem(SESSION_KEY)
    setSessionId(null)
    return startNewSession()
  }, [startNewSession])

  return { sessionId, loading, error, resetSession }
}
