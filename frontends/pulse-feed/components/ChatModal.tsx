'use client'
import { useState, useRef, useEffect } from 'react'
import styles from './ChatModal.module.css'

const MODELS = [
  { value: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite' },
  { value: 'gemini-2.5-flash',              label: 'Gemini 2.5 Flash' },
  { value: 'gemini-2.5-pro',               label: 'Gemini 2.5 Pro' },
  { value: 'gemini-2.0-flash',             label: 'Gemini 2.0 Flash (unsupported)' },
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
  trace_id?: string
  feedback?: 'good' | 'bad'
}

interface Props {
  onClose: () => void
  city?: string
}

export default function ChatModal({ onClose, city }: Props) {
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
    console.info(`[pulse-feed] Chat message sent: model=${model} length=${msg.length}`)
    try {
      const res = await fetch(`${TEST_SVC}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, model, city }),
      })
      if (!res.ok) {
        let detail = `Request failed (${res.status})`
        try { const body = await res.json(); if (body.detail) detail = body.detail } catch {}
        throw new Error(detail)
      }
      const data = await res.json()
      console.info(`[pulse-feed] Chat response received: model=${data.model} trace_id=${data.trace_id}`)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.reply,
        model: data.model,
        trace_id: data.trace_id,
      }])
    } catch (e: any) {
      console.error(`[pulse-feed] Chat request failed: model=${model} error=${e}`)
      setMessages(prev => [...prev, { role: 'assistant', content: e?.message || 'Something went wrong. Please try again.' }])
    } finally {
      setLoading(false)
    }
  }

  const sendFeedback = async (index: number, rating: 'good' | 'bad') => {
    const msg = messages[index]
    if (!msg.trace_id || msg.feedback) return

    setMessages(prev => prev.map((m, i) => i === index ? { ...m, feedback: rating } : m))
    console.info(`[pulse-feed] Chat feedback: rating=${rating} trace_id=${msg.trace_id}`)

    try {
      await fetch(`${TEST_SVC}/chat/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trace_id: msg.trace_id, rating }),
      })
    } catch (e) {
      console.error(`[pulse-feed] Chat feedback failed: ${e}`)
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
              {m.role === 'assistant' && m.trace_id && (
                <div className={styles.feedback}>
                  <button
                    className={`${styles.feedbackBtn} ${m.feedback === 'good' ? styles.feedbackActive : ''}`}
                    onClick={() => sendFeedback(i, 'good')}
                    disabled={!!m.feedback}
                    title="Good response"
                  >
                    👍
                  </button>
                  <button
                    className={`${styles.feedbackBtn} ${m.feedback === 'bad' ? styles.feedbackActive : ''}`}
                    onClick={() => sendFeedback(i, 'bad')}
                    disabled={!!m.feedback}
                    title="Bad response"
                  >
                    👎
                  </button>
                </div>
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
