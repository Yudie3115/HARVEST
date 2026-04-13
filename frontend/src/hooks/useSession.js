import { useState, useEffect } from 'react'
import { createSession } from '../api'

const SESSION_KEY = 'ph_session_id'

export function useSession() {
  const [sessionId, setSessionId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const stored = localStorage.getItem(SESSION_KEY)
    if (stored) {
      setSessionId(stored)
      setLoading(false)
      return
    }

    createSession('web')
      .then(({ session_id }) => {
        localStorage.setItem(SESSION_KEY, session_id)
        setSessionId(session_id)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  return { sessionId, loading, error }
}
