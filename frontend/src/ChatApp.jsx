import { useState } from 'react'
import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import LanguageBar from './components/LanguageBar'
import InputBar from './components/InputBar'
import SourcesSidebar from './components/SourcesSidebar'
import { useSession } from './hooks/useSession'
import { useChat } from './hooks/useChat'

export default function App() {
  const { sessionId, loading: sessionLoading } = useSession()
  const { messages, isLoading, detectedLanguage, languageOverride, setLanguageOverride, modelPreference, setModelPreference, send } =
    useChat(sessionId)

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
        onModelChange={setModelPreference}
      />
      <InputBar onSend={send} disabled={isLoading || sessionLoading || !sessionId} />

      <SourcesSidebar sources={activeSources} onClose={() => setActiveSources(null)} />
    </div>
  )
}
