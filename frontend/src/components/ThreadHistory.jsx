import { Clock3, History, MessageSquareText, Plus, X } from 'lucide-react'

function formatThreadDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const threadDay = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const dayDifference = Math.round((today - threadDay) / 86_400_000)
  const time = new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)

  if (dayDifference === 0) return `Today, ${time}`
  if (dayDifference === 1) return `Yesterday, ${time}`
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  }).format(date)
}

function HistoryPanel({
  threads,
  currentSessionId,
  loading,
  error,
  newChatDisabled,
  threadSwitchDisabled,
  onSelect,
  onNewChat,
  onClose,
}) {
  return (
    <>
      <div className="flex h-[67px] shrink-0 items-center justify-between border-b border-[#27342b] px-4">
        <div>
          <div className="flex items-center gap-2 text-[#d9d4ca]">
            <History size={15} />
            <h2 className="m-0 font-display text-[17px] font-medium">History</h2>
          </div>
          <p className="mb-0 mt-1 font-mono text-[8px] uppercase tracking-[0.12em] text-[#637168]">
            Saved conversation threads
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close history"
            className="grid h-9 w-9 place-items-center border border-transparent text-[#78857c] hover:border-[#344239] hover:text-[#e8e4da] focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#6ab08a]"
          >
            <X size={17} />
          </button>
        )}
      </div>

      <div className="shrink-0 p-3">
        <button
          type="button"
          onClick={onNewChat}
          disabled={newChatDisabled}
          className="flex w-full items-center justify-center gap-2 border border-[#477456] bg-[#1a2d20] px-3 py-2.5 text-xs font-semibold text-[#a9d8b9] transition-colors hover:bg-[#213927] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#6ab08a] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus size={14} />
          New chat
        </button>
      </div>

      <nav aria-label="Chat history" className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        {loading && (
          <div className="space-y-2 px-2 py-1" aria-label="Loading chat history">
            {[0, 1, 2].map((item) => (
              <div key={item} className="h-[66px] animate-pulse border-l border-[#29342d] bg-[#141a16]" />
            ))}
          </div>
        )}
        {!loading && error && (
          <p className="mx-2 border-l-2 border-[#876f3e] bg-[#19170f] px-3 py-3 text-xs leading-5 text-[#bda66e]">
            {error}
          </p>
        )}
        {!loading && !error && threads.length === 0 && (
          <div className="mx-2 mt-2 border border-dashed border-[#303a33] px-4 py-7 text-center">
            <MessageSquareText className="mx-auto text-[#526158]" size={20} />
            <p className="mb-0 mt-3 text-xs leading-5 text-[#707c74]">
              Your saved chats will appear here.
            </p>
          </div>
        )}
        {!loading && threads.map((thread) => {
          const active = thread.session_id === currentSessionId
          return (
            <button
              key={thread.session_id}
              type="button"
              onClick={() => onSelect(thread.session_id)}
              disabled={threadSwitchDisabled}
              aria-current={active ? 'page' : undefined}
              className={`group relative mb-1 w-full border-0 px-3 py-3 text-left transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#6ab08a] disabled:cursor-not-allowed disabled:opacity-50 ${
                active ? 'bg-[#19241d]' : 'bg-transparent hover:bg-[#141b17]'
              }`}
            >
              <span
                className={`absolute bottom-2 left-0 top-2 w-px ${
                  active ? 'bg-[#d4a853]' : 'bg-[#29342d] group-hover:bg-[#415247]'
                }`}
                aria-hidden="true"
              />
              <span className={`block truncate text-[13px] leading-5 ${
                active ? 'text-[#e7e1d6]' : 'text-[#aeb6af]'
              }`}>
                {thread.title}
              </span>
              <span className="mt-1.5 flex items-center justify-between gap-2 font-mono text-[8px] uppercase tracking-[0.06em] text-[#59665e]">
                <span className="flex min-w-0 items-center gap-1">
                  <Clock3 size={9} />
                  <span className="truncate">{formatThreadDate(thread.updated_at)}</span>
                </span>
                <span>{thread.message_count} msg</span>
              </span>
            </button>
          )
        })}
      </nav>
    </>
  )
}

export default function ThreadHistory({
  threads,
  currentSessionId,
  loading,
  error,
  open,
  newChatDisabled,
  threadSwitchDisabled,
  onOpen,
  onClose,
  onSelect,
  onNewChat,
}) {
  const panelProps = {
    threads,
    currentSessionId,
    loading,
    error,
    newChatDisabled,
    threadSwitchDisabled,
    onSelect,
    onNewChat,
  }

  return (
    <>
      <aside className="hidden w-[286px] shrink-0 flex-col border-r border-[#27342b] bg-[#0d1310] md:flex">
        <HistoryPanel {...panelProps} />
      </aside>

      <div className="flex h-11 shrink-0 items-center justify-between border-b border-[#202c24] bg-[#0e1511] px-3 md:hidden">
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex items-center gap-2 px-1 py-2 text-xs text-[#aeb8b0] focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#6ab08a]"
        >
          <History size={14} />
          History
          <span className="font-mono text-[9px] text-[#5f6d64]">{threads.length}</span>
        </button>
        <button
          type="button"
          onClick={onNewChat}
          disabled={newChatDisabled}
          className="inline-flex items-center gap-1.5 border border-[#365b43] px-2.5 py-1.5 text-[11px] text-[#9ed0ae] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus size={12} />
          New chat
        </button>
      </div>

      <button
        type="button"
        aria-label="Close history"
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-black/60 transition-opacity md:hidden ${
          open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        aria-label="Chat history"
        aria-hidden={!open}
        inert={open ? undefined : ''}
        className={`fixed bottom-0 left-0 top-0 z-50 flex w-[min(320px,88vw)] flex-col border-r border-[#304036] bg-[#0d1310] shadow-[18px_0_50px_rgba(0,0,0,0.42)] transition-transform duration-200 md:hidden ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <HistoryPanel {...panelProps} onClose={onClose} />
      </aside>
    </>
  )
}
