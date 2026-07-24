export const LIVE_HANDOFF_KEY = 'phk_live_handoff'
export const PENDING_QUESTION_KEY = 'phk_pending_question'

export function readStoredJson(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null')
  } catch {
    localStorage.removeItem(key)
    return null
  }
}
