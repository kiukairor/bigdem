'use client'
import { useState, useRef, useEffect } from 'react'
import styles from './ChatModal.module.css'

const MODELS = [
  { value: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite' },
  { value: 'gemini-2.0-flash',              label: 'Gemini 2.0 Flash' },
  { value: 'gemini-2.0-flash-lite',         label: 'Gemini 2.0 Flash Lite' },
  { value: 'gemini-1.5-flash',              label: 'Gemini 1.5 Flash' },
  { value: 'gemini-1.5-pro',               label: 'Gemini 1.5 Pro' },
  { value: 'claude-sonnet-4-6',            label: 'Claude Sonnet 4.6' },
  { value: 'claude-haiku-4-5-20251001',    label: 'Claude Haiku 4.5' },
  { value: 'gpt-4o-mini',                  label: 'GPT-4o Mini' },
  { value: 'gpt-4.1-nano',                 label: 'GPT-4.1 Nano' },
]

const TEST_SVC = process.env.NEXT_PUBLIC_TEST_SVC_URL || 'http://localhost:8090'

interface Message {
  role: 'user' | 'assistant'
  content: string
  model?: string
}

interface Props {
  onClose: () => void
}

export default function ChatModal({ onClose }: Props) {
  const [messages, setMessages]   = useState<Message[]>([])
  const [input, setInput]         = useState('')
  const [model, setModel]         = useState(MODELS[0].value)
  const [loading, setLoading]     = useState(false)
  const bottomRef                 = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)
    try {
      const res = await fetch(`${TEST_SVC}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, model }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply, model: data.model }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Something went wrong. Please try again.' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.header}>
          <span className={styles.title}>PULSE ASSISTANT</span>
          <select
            className={styles.modelSelect}
            value={model}
            onChange={e => setModel(e.target.value)}
          >
            {MODELS.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
          <button className={styles.close} onClick={onClose}>✕</button>
        </div>

        <div className={styles.messages}>
          {messages.length === 0 && !loading && (
            <p className={styles.empty}>Ask me about events in any city.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`${styles.msg} ${m.role === 'user' ? styles.user : styles.assistant}`}>
              <p className={styles.msgContent}>{m.content}</p>
              {m.role === 'assistant' && m.model && (
                <span className={styles.msgModel}>{m.model}</span>
              )}
            </div>
          ))}
          {loading && (
            <div className={`${styles.msg} ${styles.assistant}`}>
              <span className={styles.typing}>
                <span /><span /><span />
              </span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className={styles.inputRow}>
          <input
            className={styles.input}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Ask about events..."
            disabled={loading}
            autoFocus
          />
          <button
            className={styles.send}
            onClick={send}
            disabled={loading || !input.trim()}
          >
            SEND
          </button>
        </div>
      </div>
    </div>
  )
}
