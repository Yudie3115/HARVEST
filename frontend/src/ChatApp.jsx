import { useCallback, useState } from 'react'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import LanguageBar from './components/LanguageBar'
import InputBar from './components/InputBar'
import SourcesSidebar from './components/SourcesSidebar'
import { useSession } from './hooks/useSession'
import { useChat } from './hooks/useChat'
import AccessGate, { formatReset } from './access/AccessGate'
import { useAccess } from './access/AccessContext'
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
  const [handoff, setHandoff] = useState(() => readStoredJson(LIVE_HANDOFF_KEY))
  const clearHandoff = useCallback(() => {
    localStorage.removeItem(LIVE_HANDOFF_KEY)
    setHandoff(null)
  }, [])
  const { sessionId, loading: sessionLoading, resetSession } = useSession(
    access.token,
    handoff?.sessionId,
    { onAccessError: access.reportAccessError },
  )
  const { messages, isLoading, detectedLanguage, languageOverride, setLanguageOverride, modelPreference, setModelPreference, modelOptions, send } =
    useChat(sessionId, {
      token: access.token,
      initialQuestion: handoff?.question,
      sendingEnabled: access.canChat,
      onInitialQuestionConsumed: clearHandoff,
      onSessionExpired: resetSession,
      onAccessError: access.reportAccessError,
    })

  const [activeSources, setActiveSources] = useState(null)

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
        <>
          <ChatWindow
            messages={messages}
            isLoading={isLoading || sessionLoading}
            onShowSources={setActiveSources}
            onAskQuestion={send}
            interactionsDisabled={isLoading || sessionLoading || !access.canChat}
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
              <InputBar onSend={send} disabled={isLoading || sessionLoading || !sessionId} />
            </>
          ) : (
            <ReadOnlyNotice
              state={access.state}
              periodResetsAt={access.details?.period_resets_at}
            />
          )}
        </>
      ) : (
        <main className="flex-1 overflow-y-auto px-4 py-10">
          <AccessGate compact onGranted={() => {}} />
        </main>
      )}

      <SourcesSidebar sources={activeSources} onClose={() => setActiveSources(null)} />
    </div>
  )
}
