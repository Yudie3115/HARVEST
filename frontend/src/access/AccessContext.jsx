import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getAccessStatus, redeemAccessCode } from '../api'

const TOKEN_KEY = 'phk_access_token'
const AccessContext = createContext(null)

function stateFromStatus(status) {
  if (status.status === 'revoked') return 'revoked'
  if (status.usage_count >= status.monthly_limit) return 'exhausted'
  return 'active'
}

export function AccessProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [state, setState] = useState(token ? 'loading' : 'absent')
  const [details, setDetails] = useState(null)
  const [error, setError] = useState(null)

  const validate = useCallback(async (candidate = token) => {
    if (!candidate) {
      setState('absent')
      setDetails(null)
      return null
    }
    setState('loading')
    try {
      const status = await getAccessStatus(candidate)
      setDetails(status)
      setError(null)
      setState(stateFromStatus(status))
      return status
    } catch (err) {
      if (['access_invalid', 'access_required'].includes(err.code)) {
        localStorage.removeItem(TOKEN_KEY)
        setToken(null)
        setDetails(null)
        setState('invalid')
      } else {
        setState('unavailable')
      }
      setError(err)
      return null
    }
  }, [token])

  useEffect(() => {
    validate()
  }, [validate])

  useEffect(() => {
    function onVisibility() {
      if (document.visibilityState === 'visible' && token) validate(token)
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [token, validate])

  const redeem = useCallback(async (code) => {
    setState('redeeming')
    setError(null)
    try {
      const result = await redeemAccessCode(code)
      localStorage.setItem(TOKEN_KEY, result.access_token)
      setToken(result.access_token)
      const nextDetails = {
        status: 'active',
        label: result.label,
        monthly_limit: result.monthly_limit,
        usage_count: result.usage_count,
        period_resets_at: result.period_resets_at,
      }
      setDetails(nextDetails)
      setState(stateFromStatus(nextDetails))
      return result.access_token
    } catch (err) {
      setError(err)
      setState(err.code === 'redemption_rate_limited' ? 'rate_limited' : 'code_error')
      throw err
    }
  }, [])

  const removeAccess = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem('ph_session_id')
    setToken(null)
    setDetails(null)
    setError(null)
    setState('absent')
  }, [])

  const reportAccessError = useCallback((err) => {
    if (!err?.code) return
    setError(err)
    if (['access_invalid', 'access_required'].includes(err.code)) {
      localStorage.removeItem(TOKEN_KEY)
      setToken(null)
      setDetails(null)
      setState('invalid')
    } else if (err.code === 'access_revoked') {
      setState('revoked')
    } else if (err.code === 'quota_exhausted') {
      setDetails((current) => ({
        ...(current || {}),
        period_resets_at: err.periodResetsAt || current?.period_resets_at,
      }))
      setState('exhausted')
    } else if (err.code === 'global_limit_reached') {
      setState('global_unavailable')
    }
  }, [])

  const value = useMemo(() => ({
    token,
    state,
    details,
    error,
    redeem,
    validate,
    removeAccess,
    reportAccessError,
    canChat: state === 'active',
  }), [token, state, details, error, redeem, validate, removeAccess, reportAccessError])

  return <AccessContext.Provider value={value}>{children}</AccessContext.Provider>
}

export function useAccess() {
  const context = useContext(AccessContext)
  if (!context) throw new Error('useAccess must be used inside AccessProvider')
  return context
}
