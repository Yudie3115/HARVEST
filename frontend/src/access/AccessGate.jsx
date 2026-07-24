import { useState } from 'react'
import { AlertTriangle, KeyRound, Loader2, LockKeyhole } from 'lucide-react'
import { useAccess } from './AccessContext'

function formatReset(value) {
  if (!value) return 'the next monthly reset'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'long',
    timeStyle: 'short',
  }).format(new Date(value))
}

export default function AccessGate({ onGranted, onCancel, onCancelLabel = 'Return to Ask', compact = false }) {
  const { state, details, error, redeem, removeAccess } = useAccess()
  const [code, setCode] = useState('')
  const [replacement, setReplacement] = useState(false)
  const showForm = ['absent', 'invalid', 'code_error', 'rate_limited'].includes(state)
    || replacement

  async function submit(event) {
    event.preventDefault()
    if (!code.trim()) return
    try {
      const token = await redeem(code.trim())
      setCode('')
      onGranted?.(token)
    } catch {
      // The shared context renders the stable error state.
    }
  }

  return (
    <section className={`mx-auto w-full ${compact ? 'max-w-[560px]' : 'max-w-[620px]'} animate-fade-up`}>
      <div className="border border-[#304036] bg-[#111a14] shadow-[0_18px_60px_rgba(0,0,0,0.24)]">
        <div className="border-b border-[#28342d] px-5 py-4 sm:px-7">
          <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-full border border-[#3d5b47] bg-[#18271d] text-[#8ecfaa]">
            {state === 'exhausted' || state === 'revoked' ? <LockKeyhole size={16} /> : <KeyRound size={16} />}
          </div>
          <h2 className="m-0 font-display text-[22px] font-medium text-[#e8e4da]">
            {state === 'revoked'
              ? 'This access has been paused.'
              : state === 'exhausted'
                ? 'This month’s live messages are used.'
                : state === 'global_unavailable'
                  ? 'Live chat is temporarily unavailable.'
                  : 'Live chat needs an access code.'}
          </h2>
          <p className="mb-0 mt-2 text-[13px] leading-5 text-[#8a9489]">
            {state === 'exhausted'
              ? `Your access remains saved and will work again after ${formatReset(details?.period_resets_at)}.`
              : state === 'revoked'
                ? 'Your saved code can be reactivated by its administrator, or you can use a replacement code.'
                : state === 'global_unavailable'
                  ? 'The system-wide message allowance has been reached. Published documents and catalogue answers remain available.'
                  : 'Enter the three-word code issued by your administrator. Browsing the library and catalogue remains free.'}
          </p>
        </div>

        <div className="px-5 py-5 sm:px-7">
          {state === 'loading' && (
            <p className="m-0 flex items-center gap-2 text-sm text-[#8a9489]">
              <Loader2 size={15} className="animate-spin" /> Checking saved access…
            </p>
          )}
          {state === 'unavailable' && (
            <p className="m-0 text-sm text-[#d7a55e]">
              Access could not be verified. Check your connection and try again.
            </p>
          )}
          {showForm && (
            <form onSubmit={submit}>
              <label htmlFor="access-code" className="mb-2 block font-mono text-[10px] uppercase tracking-[0.16em] text-[#879188]">
                Three-word access code
              </label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  id="access-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  autoComplete="off"
                  spellCheck="false"
                  placeholder="mango-river-granary"
                  className="min-w-0 flex-1 rounded-md border border-[#344139] bg-[#0d140f] px-4 py-3 font-mono text-sm text-[#e8e4da] outline-none placeholder:text-[#4d5850] focus:border-[#5c8068]"
                />
                <button
                  type="submit"
                  disabled={!code.trim() || state === 'redeeming'}
                  className="inline-flex min-w-[120px] items-center justify-center gap-2 rounded-md bg-[#6ab08a] px-4 py-3 text-sm font-semibold text-[#0b160e] transition-colors hover:bg-[#83c59f] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {state === 'redeeming' && <Loader2 size={14} className="animate-spin" />}
                  Continue
                </button>
              </div>
              {['code_error', 'rate_limited', 'invalid'].includes(state) && (
                <p className="mb-0 mt-3 flex items-start gap-2 text-xs leading-5 text-[#d7a55e]">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  {error?.message || 'That saved access token is no longer valid. Enter your code again.'}
                </p>
              )}
            </form>
          )}

          {!showForm && state === 'revoked' && (
            <button onClick={() => setReplacement(true)} className="text-xs text-[#8ecfaa] underline underline-offset-4">
              Use a replacement code
            </button>
          )}
          {['exhausted', 'global_unavailable'].includes(state) && (
            <button onClick={removeAccess} className="text-xs text-[#77827a] underline underline-offset-4">
              Remove saved access
            </button>
          )}
          {onCancel && (
            <button onClick={onCancel} className="ml-5 text-xs text-[#77827a] hover:text-[#d4cfc6]">
              {onCancelLabel}
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
