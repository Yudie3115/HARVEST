import { useCallback, useEffect, useState } from 'react'
import { createSession, getHistory } from '../api'

const SESSION_KEY = 'ph_session_id'

export function useSession() {
  const [sessionId, setSessionId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const startNewSession = useCallback(() => {
    setLoading(true)
    setError(null)
    return createSession('web')
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
  }, [])

  useEffect(() => {
    const stored = localStorage.getItem(SESSION_KEY)
    if (!stored) {
      startNewSession().catch(() => {})
      return
    }

    getHistory(stored)
      .then(() => {
        setSessionId(stored)
        setLoading(false)
      })
      .catch((err) => {
        if (err.status === 404 || err.status === 422) {
          localStorage.removeItem(SESSION_KEY)
          startNewSession().catch(() => {})
          return
        }
        setSessionId(stored)
        setError(err.message)
        setLoading(false)
      })
  }, [startNewSession])

  const resetSession = useCallback(() => {
    localStorage.removeItem(SESSION_KEY)
    setSessionId(null)
    return startNewSession()
  }, [startNewSession])

  return { sessionId, loading, error, resetSession }
}
