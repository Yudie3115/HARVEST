import Header from './components/Header'
import ChatWindow from './components/ChatWindow'
import LanguageBar from './components/LanguageBar'
import InputBar from './components/InputBar'
import { useSession } from './hooks/useSession'
import { useChat } from './hooks/useChat'

export default function App() {
  const { sessionId, loading: sessionLoading } = useSession()
  const { messages, isLoading, detectedLanguage, languageOverride, setLanguageOverride, send } =
    useChat(sessionId)

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
      <Header languageOverride={languageOverride} onLanguageChange={setLanguageOverride} />
      <ChatWindow messages={messages} isLoading={isLoading || sessionLoading} />
      <LanguageBar
        detectedLanguage={detectedLanguage}
        languageOverride={languageOverride}
        onOverride={setLanguageOverride}
      />
      <InputBar onSend={send} disabled={isLoading || sessionLoading || !sessionId} />
    </div>
  )
}
