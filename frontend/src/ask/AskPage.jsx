import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowRight, BookOpen, Check, ExternalLink, Loader2, RotateCcw } from 'lucide-react'
import Header from '../components/Header'
import AccessGate from '../access/AccessGate'
import { useAccess } from '../access/AccessContext'
import {
  createCatalogueSession,
  createSession,
  markCatalogueHelpful,
  markCatalogueRejectedMatch,
  matchCatalogue,
} from '../api'
import { mdComponents } from '../lib/markdownComponents'
import { isSafeUrl } from '../lib/sanitize'
import { LIVE_HANDOFF_KEY, PENDING_QUESTION_KEY, readStoredJson } from './handoff'

export default function AskPage() {
  const navigate = useNavigate()
  const access = useAccess()
  const restored = useRef(readStoredJson(PENDING_QUESTION_KEY))
  const launching = useRef(false)
  const [question, setQuestion] = useState(restored.current?.question || '')
  const [phase, setPhase] = useState(restored.current ? 'gate' : 'idle')
  const [match, setMatch] = useState(null)
  const [pending, setPending] = useState(restored.current)
  const [followUp, setFollowUp] = useState('')
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [error, setError] = useState(null)

  async function submitQuestion(event) {
    event.preventDefault()
    const text = question.trim()
    if (!text) return
    setPhase('matching')
    setError(null)
    setMatch(null)
    try {
      const result = await matchCatalogue(text)
      if (result.matched) {
        setMatch(result.entry)
        setPhase('matched')
      } else {
        requestLive({ question: text, catalogueEntryId: null })
      }
    } catch (err) {
      setError(err.message)
      setPhase('error')
    }
  }

  function requestLive(next) {
    setPending(next)
    localStorage.setItem(PENDING_QUESTION_KEY, JSON.stringify(next))
    setPhase('gate')
    if (access.canChat) launchLive(next, access.token)
  }

  async function launchLive(next = pending, token = access.token) {
    if (!next || !token || launching.current) return
    launching.current = true
    setPhase('starting_chat')
    try {
      const session = next.catalogueEntryId
        ? await createCatalogueSession(next.catalogueEntryId, token)
        : await createSession('web', token)
      localStorage.setItem('ph_session_id', session.session_id)
      localStorage.setItem(
        LIVE_HANDOFF_KEY,
        JSON.stringify({ sessionId: session.session_id, question: next.question }),
      )
      localStorage.removeItem(PENDING_QUESTION_KEY)
      navigate('/chat')
    } catch (err) {
      launching.current = false
      access.reportAccessError(err)
      setError(err.message)
      setPhase('gate')
    }
  }

  useEffect(() => {
    if (phase === 'gate' && pending && access.canChat) launchLive(pending, access.token)
    // launchLive is guarded by a ref; rerunning after access validation is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [access.canChat, access.token, phase, pending])

  function reset() {
    localStorage.removeItem(PENDING_QUESTION_KEY)
    setQuestion('')
    setPending(null)
    setMatch(null)
    setFollowUp('')
    setFeedbackSent(false)
    setError(null)
    setPhase('idle')
  }

  async function helpful() {
    if (!match || feedbackSent) return
    await markCatalogueHelpful(match.id)
    setFeedbackSent(true)
  }

  async function rejectMatch() {
    if (!match) return
    try {
      await markCatalogueRejectedMatch(match.id)
    } catch {
      // Feedback telemetry must never block the live-chat handoff.
    }
    requestLive({ question: question.trim(), catalogueEntryId: null })
  }

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-[#111613]">
      <Header />
      <main className="overflow-y-auto px-4 pb-16 pt-8 sm:pt-12">
        <div className="mx-auto max-w-[780px]">
          {['idle', 'matching', 'error'].includes(phase) && (
            <section className="animate-fade-up">
              <div className="mb-10 max-w-[650px]">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-[#d4a853]">
                  Trusted post-harvest guidance
                </p>
                <h1 className="m-0 font-display text-[clamp(32px,6vw,52px)] font-medium leading-[1.05] tracking-[-0.025em] text-[#e8e4da]">
                  Start with what the knowledge base already knows.
                </h1>
                <p className="mb-0 mt-5 max-w-[590px] text-[15px] leading-6 text-[#8a9489]">
                  Ask one practical question. We’ll check reviewed answers first, then use live chat only when it adds something new.
                </p>
              </div>

              <form onSubmit={submitQuestion} className="border-y border-[#334039] bg-[#121a15] px-1 py-2">
                <label htmlFor="ask-question" className="sr-only">Your post-harvest question</label>
                <textarea
                  id="ask-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      event.currentTarget.form?.requestSubmit()
                    }
                  }}
                  rows={3}
                  maxLength={1000}
                  autoFocus
                  placeholder="How can I keep dried maize free from weevils?"
                  className="block w-full resize-none border-0 bg-transparent px-4 py-4 font-display text-[22px] leading-8 text-[#e8e4da] outline-none placeholder:text-[#4f5b52] sm:text-[25px]"
                />
                <div className="flex items-center justify-between gap-3 border-t border-[#28342d] px-4 py-3">
                  <span className="text-[11px] text-[#657168]">English or a supported Ugandan language</span>
                  <button
                    type="submit"
                    disabled={!question.trim() || phase === 'matching'}
                    className="inline-flex items-center gap-2 rounded-md bg-[#6ab08a] px-4 py-2.5 text-sm font-semibold text-[#0b160e] hover:bg-[#83c59f] disabled:opacity-50"
                  >
                    {phase === 'matching' ? <Loader2 size={15} className="animate-spin" /> : <ArrowRight size={15} />}
                    Check for an answer
                  </button>
                </div>
              </form>

              {error && (
                <p className="mt-4 text-sm text-[#d4a853]">
                  {error} <button onClick={() => setPhase('idle')} className="underline">Try again</button>
                </p>
              )}
              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                <button onClick={() => navigate('/documents')} className="flex items-center gap-3 border border-[#28342d] px-4 py-4 text-left hover:bg-[#141d17]">
                  <BookOpen size={17} className="text-[#7aa78a]" />
                  <span><b className="block text-sm font-medium text-[#d4cfc6]">Browse documents</b><small className="text-[#68736b]">Published source material</small></span>
                </button>
                <button onClick={() => navigate('/catalogue')} className="flex items-center gap-3 border border-[#28342d] px-4 py-4 text-left hover:bg-[#141d17]">
                  <Check size={17} className="text-[#d4a853]" />
                  <span><b className="block text-sm font-medium text-[#d4cfc6]">Browse reviewed answers</b><small className="text-[#68736b]">Reusable questions and citations</small></span>
                </button>
              </div>
            </section>
          )}

          {phase === 'matched' && match && (
            <section className="animate-fade-up">
              <button onClick={reset} className="mb-7 inline-flex items-center gap-2 text-xs text-[#819086]">
                <RotateCcw size={13} /> Ask another question
              </button>
              <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-[#d4a853]">Reviewed catalogue match</p>
              <h1 className="mb-7 mt-0 font-display text-[28px] font-medium leading-tight text-[#e8e4da]">{match.question}</h1>
              <div className="border-l-2 border-[#568164] bg-[#141a15] px-5 py-5 text-sm text-[#d4cfc6]">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{match.answer}</ReactMarkdown>
              </div>
              {match.sources?.some((source) => isSafeUrl(source.url)) && (
                <div className="mt-5 flex flex-wrap gap-2">
                  {match.sources.filter((source) => isSafeUrl(source.url)).map((source, index) => (
                    <a key={`${source.url}-${index}`} href={source.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-full border border-[#344139] px-3 py-1.5 text-[11px] text-[#9bab9e] no-underline">
                      {source.title || source.site_name || 'Source'} <ExternalLink size={10} />
                    </a>
                  ))}
                </div>
              )}
              <div className="mt-7 border-t border-[#2a3329] pt-5">
                <div className="flex flex-wrap items-center gap-3">
                  <button onClick={helpful} disabled={feedbackSent} className="inline-flex items-center gap-2 rounded-md border border-[#3d6b4f] px-3 py-2 text-xs text-[#8ecfaa] disabled:opacity-60">
                    <Check size={13} /> {feedbackSent ? 'Marked helpful' : 'This answered it'}
                  </button>
                  <button onClick={rejectMatch} className="text-xs text-[#b58c50] underline underline-offset-4">
                    This doesn’t answer my question
                  </button>
                </div>
                <form
                  onSubmit={(event) => {
                    event.preventDefault()
                    if (followUp.trim()) requestLive({ question: followUp.trim(), catalogueEntryId: match.id })
                  }}
                  className="mt-6 flex flex-col gap-2 sm:flex-row"
                >
                  <input value={followUp} onChange={(event) => setFollowUp(event.target.value)} placeholder="Ask a follow-up about this answer…" className="min-w-0 flex-1 rounded-md border border-[#344139] bg-[#0d140f] px-4 py-3 text-sm text-[#e8e4da] outline-none focus:border-[#5c8068]" />
                  <button disabled={!followUp.trim()} className="rounded-md bg-[#263c2d] px-4 py-3 text-sm text-[#a8d6b8] disabled:opacity-40">Continue in live chat</button>
                </form>
              </div>
            </section>
          )}

          {['gate', 'starting_chat'].includes(phase) && (
            <div className="animate-fade-up">
              <p className="mb-5 text-center font-mono text-[10px] uppercase tracking-[0.18em] text-[#738078]">
                Your question is saved
              </p>
              {phase === 'starting_chat' ? (
                <div className="flex items-center justify-center gap-3 py-16 text-sm text-[#8a9489]"><Loader2 size={17} className="animate-spin" /> Preparing live chat…</div>
              ) : (
                <AccessGate
                  onGranted={(token) => launchLive(pending, token)}
                  onCancel={match
                    ? () => {
                        localStorage.removeItem(PENDING_QUESTION_KEY)
                        setPending(null)
                        setPhase('matched')
                    }
                    : reset}
                  onCancelLabel={match ? 'Return to the answer' : 'Return to Ask'}
                />
              )}
              {error && <p className="mt-4 text-center text-xs text-[#d4a853]">{error}</p>}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
