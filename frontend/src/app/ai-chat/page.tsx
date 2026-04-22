'use client'

import { useState, useRef, useEffect, useCallback } from 'react'

const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  loading?: boolean
}

const QUICK_PROMPTS = [
  'Analyse current substation efficiency',
  'Explain the top causes of energy loss',
  'Predict peak load for next 24 hours',
  'What anomalies were detected today?',
  'Summarise grid health status',
]

async function* streamAIResponse(substationId: string, message: string): AsyncGenerator<string> {
  // Use the new /chat endpoint for conversational AI responses
  const token = typeof window !== 'undefined' ? localStorage.getItem('urjarakshak_token') : null
  if (!token) {
    throw new Error('Authentication required. Please log in at /login to use the AI assistant.')
  }
  const headers: Record<string, string> = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }

  try {
    const res = await fetch(`${BASE}/api/v1/ai/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ substation_id: substationId, question: message }),
    })

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body?.detail || `HTTP ${res.status}`)
    }

    const json = await res.json()
    const text: string = json?.answer || json?.interpretation || json?.result || JSON.stringify(json, null, 2)

    // Simulate typewriter effect
    const words = text.split(' ')
    for (const word of words) {
      yield word + ' '
      await new Promise((r) => setTimeout(r, 18))
    }
  } catch (err: any) {
    throw new Error(err?.message || 'Failed to reach AI service')
  }
}

let msgCounter = 0
function newId() {
  return `msg-${++msgCounter}-${Date.now()}`
}

export default function AiChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        'Hello! I am the UrjaRakshak AI assistant. I can help you analyse grid health, explain energy loss patterns, interpret anomalies, and forecast load. Which substation should I focus on, or ask me anything about the grid.',
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [substationId, setSubstationId] = useState('demo-sub-01')
  const [isStreaming, setIsStreaming] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return
      setInput('')

      const userMsg: Message = {
        id: newId(),
        role: 'user',
        content: text.trim(),
        timestamp: new Date(),
      }

      const aiPlaceholder: Message = {
        id: newId(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        loading: true,
      }

      setMessages((prev) => [...prev, userMsg, aiPlaceholder])
      setIsStreaming(true)

      try {
        let accumulated = ''
        for await (const chunk of streamAIResponse(substationId, text.trim())) {
          accumulated += chunk
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aiPlaceholder.id ? { ...m, content: accumulated, loading: false } : m
            )
          )
        }
        if (!accumulated) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aiPlaceholder.id
                ? { ...m, content: 'No response received from AI service.', loading: false }
                : m
            )
          )
        }
      } catch (err: any) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiPlaceholder.id
              ? { ...m, content: `Error: ${err?.message || 'Unknown error'}`, loading: false }
              : m
          )
        )
      } finally {
        setIsStreaming(false)
      }
    },
    [isStreaming, substationId]
  )

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  function formatTime(d: Date) {
    return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <main className="page" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - var(--nav-h) - 40px)', minHeight: 600 }}>
      {/* Header */}
      <div className="page-header" style={{ flexShrink: 0 }}>
        <div>
          <h1 className="page-title">AI Grid Assistant</h1>
          <p className="page-desc">
            Ask questions about energy loss, anomalies, forecasts, and grid health. Powered by
            UrjaRakshak AI.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <label style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)' }}>
            Substation
          </label>
          <input
            className="input"
            value={substationId}
            onChange={(e) => setSubstationId(e.target.value)}
            placeholder="substation-id"
            style={{ width: 160, fontFamily: 'var(--font-mono)', fontSize: 12 }}
          />
        </div>
      </div>

      {/* Quick prompts */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16, flexShrink: 0 }}>
        {QUICK_PROMPTS.map((p) => (
          <button
            key={p}
            className="chip chip-cyan"
            style={{ cursor: 'pointer', border: 'none', background: 'rgba(0,212,255,0.08)' }}
            onClick={() => sendMessage(p)}
            disabled={isStreaming}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Message thread — enlarged */}
      <div
        className="panel"
        style={{
          flex: 1,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 20,
          padding: '24px 28px',
          marginBottom: 16,
          minHeight: 0,
          fontSize: 15,
        }}
      >
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
              gap: 6,
            }}
          >
            <div
              style={{
                maxWidth: '85%',
                padding: '12px 18px',
                borderRadius: msg.role === 'user' ? 'var(--r-lg) var(--r-lg) var(--r-xs) var(--r-lg)' : 'var(--r-lg) var(--r-lg) var(--r-lg) var(--r-xs)',
                background: msg.role === 'user' ? 'rgba(0,212,255,0.12)' : 'var(--bg-elevated)',
                border: msg.role === 'user' ? '1px solid rgba(0,212,255,0.25)' : '1px solid var(--border)',
                fontFamily: 'var(--font-ui)',
                fontSize: 15,
                lineHeight: 1.7,
                color: 'var(--text-primary)',
                wordBreak: 'break-word',
                whiteSpace: 'pre-wrap',
              }}
            >
              {msg.loading ? (
                <span
                  style={{
                    display: 'inline-flex',
                    gap: 4,
                    alignItems: 'center',
                    color: 'var(--text-tertiary)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                  }}
                >
                  <span className="thinking-dot" style={{ animationDelay: '0ms' }}>●</span>
                  <span className="thinking-dot" style={{ animationDelay: '200ms' }}>●</span>
                  <span className="thinking-dot" style={{ animationDelay: '400ms' }}>●</span>
                  <style>{`.thinking-dot{animation:pulse 1.2s ease-in-out infinite;opacity:0.3}@keyframes pulse{0%,100%{opacity:0.3}50%{opacity:1}}`}</style>
                </span>
              ) : (
                msg.content
              )}
            </div>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: 'var(--text-tertiary)',
              }}
            >
              {msg.role === 'assistant' ? 'UrjaRakshak AI' : 'You'} · {formatTime(msg.timestamp)}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div
        className="panel-elevated"
        style={{
          display: 'flex',
          gap: 12,
          alignItems: 'flex-end',
          padding: '14px 18px',
          flexShrink: 0,
        }}
      >
        <textarea
          ref={inputRef}
          className="input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about energy loss, anomalies, forecasts… (Enter to send, Shift+Enter for newline)"
          rows={3}
          disabled={isStreaming}
          style={{
            flex: 1,
            resize: 'none',
            fontFamily: 'var(--font-ui)',
            fontSize: 14,
            lineHeight: 1.5,
          }}
        />
        <button
          className="btn btn-primary"
          onClick={() => sendMessage(input)}
          disabled={isStreaming || !input.trim()}
          style={{ height: 56, minWidth: 80 }}
        >
          {isStreaming ? 'Sending…' : 'Send'}
        </button>
      </div>
    </main>
  )
}
