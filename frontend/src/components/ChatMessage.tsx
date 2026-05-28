import type { Message, PendingAction } from '../types'

interface Props {
  message: Message
  onConfirm?: (confirmed: boolean) => void
  confirmLoading?: boolean
}

function ConfirmationCard({
  action,
  onConfirm,
  loading,
}: {
  action: PendingAction
  onConfirm: (confirmed: boolean) => void
  loading: boolean
}) {
  return (
    <div className="mt-3 border border-amber-200 bg-amber-50 rounded-xl p-4">
      <div className="flex items-start gap-2 mb-3">
        <svg className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div>
          <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide mb-1">
            Action requires confirmation
          </p>
          <p className="text-sm text-slate-700">{action.description}</p>
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button
          onClick={() => onConfirm(false)}
          disabled={loading}
          className="px-4 py-1.5 text-sm font-medium text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={() => onConfirm(true)}
          disabled={loading}
          className="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors flex items-center gap-2"
        >
          {loading && (
            <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
          )}
          Confirm
        </button>
      </div>
    </div>
  )
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** Render a single line, converting **bold** spans to <strong>. */
function renderLine(line: string, key: number) {
  const parts = line.split(/(\*\*[^*]+\*\*)/)
  return (
    <span key={key}>
      {parts.map((part, i) =>
        part.startsWith('**') && part.endsWith('**')
          ? <strong key={i}>{part.slice(2, -2)}</strong>
          : part
      )}
    </span>
  )
}

/** Split on newlines and render each line, preserving blank lines as <br/>. */
function renderContent(text: string) {
  const lines = text.split('\n')
  return lines.map((line, i) => (
    <span key={i}>
      {renderLine(line, i)}
      {i < lines.length - 1 && <br />}
    </span>
  ))
}

export default function ChatMessage({ message, onConfirm, confirmLoading }: Props) {
  const isUser = message.role === 'user'
  const isError = message.role === 'error'

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[75%]">
          <div className="bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
            <p className="text-sm break-words">{renderContent(message.content)}</p>
          </div>
          <p className="text-xs text-slate-400 mt-1 text-right">{formatTime(message.timestamp)}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-3 mb-4">
      {/* Avatar */}
      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-1 ${isError ? 'bg-red-500' : 'bg-blue-600'}`}>
        {isError ? (
          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ) : (
          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        )}
      </div>

      {/* Bubble */}
      <div className="max-w-[75%]">
        <div className={`rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm ${
          isError
            ? 'bg-red-50 border border-red-200 text-red-700'
            : 'bg-white border border-slate-200 text-slate-800'
        }`}>
          <p className="text-sm break-words leading-relaxed">{renderContent(message.content)}</p>

          {message.pendingAction && onConfirm && (
            <ConfirmationCard
              action={message.pendingAction}
              onConfirm={onConfirm}
              loading={confirmLoading ?? false}
            />
          )}
        </div>
        <p className="text-xs text-slate-400 mt-1">{formatTime(message.timestamp)}</p>
      </div>
    </div>
  )
}
