import { useCallback, useState } from 'react'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import LanguageBar from './components/LanguageBar'
import InputBar from './components/InputBar'
import SourcesSidebar from './components/SourcesSidebar'
import { useSession } from './hooks/useSession'
import { useChat } from './hooks/useChat'
import AccessGate from './access/AccessGate'
import { useAccess } from './access/AccessContext'
import { LIVE_HANDOFF_KEY, readStoredJson } from './ask/handoff'

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
      {access.canChat ? (
        <>
          <ChatWindow
            messages={messages}
            isLoading={isLoading || sessionLoading}
            onShowSources={setActiveSources}
          />
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
        <main className="flex-1 overflow-y-auto px-4 py-10">
          <AccessGate compact onGranted={() => {}} />
        </main>
      )}

      <SourcesSidebar sources={activeSources} onClose={() => setActiveSources(null)} />
    </div>
  )
}
