export default function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 mb-4">
      <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 mt-1">
        <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </div>
      <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center h-5">
          <span className="typing-dot w-2 h-2 bg-slate-400 rounded-full inline-block" />
          <span className="typing-dot w-2 h-2 bg-slate-400 rounded-full inline-block" />
          <span className="typing-dot w-2 h-2 bg-slate-400 rounded-full inline-block" />
        </div>
      </div>
    </div>
  )
}
