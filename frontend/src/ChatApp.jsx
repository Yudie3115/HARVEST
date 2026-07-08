import { useState } from 'react'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import LanguageBar from './components/LanguageBar'
import InputBar from './components/InputBar'
import SourcesSidebar from './components/SourcesSidebar'
import { useSession } from './hooks/useSession'
import { useChat } from './hooks/useChat'

export default function App() {
  const { sessionId, loading: sessionLoading, resetSession } = useSession()
  const { messages, isLoading, detectedLanguage, languageOverride, setLanguageOverride, modelPreference, setModelPreference, modelOptions, send } =
    useChat(sessionId, { onSessionExpired: resetSession })

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

      <SourcesSidebar sources={activeSources} onClose={() => setActiveSources(null)} />
    </div>
  )
}
