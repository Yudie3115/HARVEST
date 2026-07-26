import { useCallback, useEffect, useState } from 'react'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import LanguageBar from './components/LanguageBar'
import InputBar from './components/InputBar'
import SourcesSidebar from './components/SourcesSidebar'
import ThreadHistory from './components/ThreadHistory'
import { useSession } from './hooks/useSession'
import { useChat } from './hooks/useChat'
import AccessGate, { formatReset } from './access/AccessGate'
import { useAccess } from './access/AccessContext'
import { getThreads } from './api'
import { LIVE_HANDOFF_KEY, readStoredJson } from './ask/handoff'

function ReadOnlyNotice({ state, periodResetsAt }) {
  const exhausted = state === 'exhausted'

  return (
    <div className="shrink-0 border-t border-[#493d27] bg-[#17160f] px-4 py-3">
      <p className="mx-auto mb-0 mt-0 max-w-[780px] text-center text-xs leading-5 text-[#c5aa74]">
        {exhausted
          ? `This month’s live messages are used. You can still read this conversation, but cannot send new messages until ${formatReset(periodResetsAt)}.`
          : 'Live chat is temporarily unavailable. You can still read this conversation, but cannot send new messages.'}
      </p>
    </div>
  )
}

export default function App() {
  const access = useAccess()
  const [threads, setThreads] = useState([])
  const [threadsLoading, setThreadsLoading] = useState(true)
  const [threadsError, setThreadsError] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [startingNew, setStartingNew] = useState(false)
  const [handoff, setHandoff] = useState(() => readStoredJson(LIVE_HANDOFF_KEY))
  const clearHandoff = useCallback(() => {
    localStorage.removeItem(LIVE_HANDOFF_KEY)
    setHandoff(null)
  }, [])
  const loadThreads = useCallback(async () => {
    if (!access.token) {
      setThreads([])
      setThreadsLoading(false)
      return
    }
    setThreadsLoading(true)
    try {
      const result = await getThreads(access.token)
      setThreads(result.items || [])
      setThreadsError(null)
    } catch (error) {
      setThreadsError(error.message)
      if ([401, 403].includes(error.status)) access.reportAccessError(error)
    } finally {
      setThreadsLoading(false)
    }
  }, [access.token, access.reportAccessError])
  const {
    sessionId,
    loading: sessionLoading,
    resetSession,
    selectSession,
  } = useSession(
    access.token,
    handoff?.sessionId,
    { onAccessError: access.reportAccessError },
  )
  const { messages, isLoading, historyReady, detectedLanguage, languageOverride, setLanguageOverride, modelPreference, setModelPreference, modelOptions, send } =
    useChat(sessionId, {
      token: access.token,
      initialQuestion: handoff?.question,
      sendingEnabled: access.canChat,
      onInitialQuestionConsumed: clearHandoff,
      onSessionExpired: resetSession,
      onAccessError: access.reportAccessError,
      onThreadUpdated: loadThreads,
    })

  const [activeSources, setActiveSources] = useState(null)
  const chatBusy = isLoading || sessionLoading || !historyReady

  useEffect(() => {
    if (sessionId) loadThreads()
  }, [sessionId, loadThreads])

  const selectThread = useCallback((nextSessionId) => {
    clearHandoff()
    setActiveSources(null)
    selectSession(nextSessionId)
    setHistoryOpen(false)
  }, [clearHandoff, selectSession])

  const startNewChat = useCallback(async () => {
    if (!access.canChat || chatBusy || startingNew) return
    setStartingNew(true)
    clearHandoff()
    setActiveSources(null)
    try {
      await resetSession()
      setHistoryOpen(false)
    } catch (error) {
      access.reportAccessError(error)
    } finally {
      setStartingNew(false)
    }
  }, [
    access.canChat,
    access.reportAccessError,
    chatBusy,
    clearHandoff,
    resetSession,
    startingNew,
  ])

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100dvh',
        background: '#111613',
        overflow: 'hidden',
      }}
    >
      <Header />
      {access.canViewChat ? (
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <ThreadHistory
            threads={threads}
            currentSessionId={sessionId}
            loading={threadsLoading}
            error={threadsError}
            open={historyOpen}
            newChatDisabled={!access.canChat || chatBusy || startingNew}
            threadSwitchDisabled={chatBusy}
            onOpen={() => setHistoryOpen(true)}
            onClose={() => setHistoryOpen(false)}
            onSelect={selectThread}
            onNewChat={startNewChat}
          />
          <section className="flex min-w-0 flex-1 flex-col">
            <ChatWindow
              messages={messages}
              isLoading={chatBusy}
              onShowSources={setActiveSources}
              onAskQuestion={send}
              interactionsDisabled={chatBusy || !access.canChat}
            />
            {access.canChat ? (
              <>
                <LanguageBar
                  detectedLanguage={detectedLanguage}
                  languageOverride={languageOverride}
                  onOverride={setLanguageOverride}
                  modelPreference={modelPreference}
                  modelOptions={modelOptions}
                  onModelChange={setModelPreference}
                />
                <InputBar onSend={send} disabled={chatBusy || !sessionId} />
              </>
            ) : (
              <ReadOnlyNotice
                state={access.state}
                periodResetsAt={access.details?.period_resets_at}
              />
            )}
          </section>
        </div>
      ) : (
        <main className="flex-1 overflow-y-auto px-4 py-10">
          <AccessGate compact onGranted={() => {}} />
        </main>
      )}

      <SourcesSidebar sources={activeSources} onClose={() => setActiveSources(null)} />
    </div>
  )
}
