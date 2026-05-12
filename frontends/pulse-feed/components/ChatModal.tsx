'use client'
import { useState, useRef, useEffect } from 'react'
import styles from './ChatModal.module.css'

export const CHAT_MODELS = [
  { value: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash Lite' },
  { value: 'gemini-2.5-flash',              label: 'Gemini 2.5 Flash' },
  { value: 'gemini-2.5-pro',               label: 'Gemini 2.5 Pro' },
  { value: 'gemini-2.0-flash',             label: 'Gemini 2.0 Flash' },
  { value: 'claude-sonnet-4-6',            label: 'Claude Sonnet 4.6' },
  { value: 'claude-haiku-4-5-20251001',    label: 'Claude Haiku 4.5' },
  { value: 'gpt-4o-mini',                  label: 'GPT-4o Mini' },
  { value: 'gpt-4.1-nano',                 label: 'GPT-4.1 Nano' },
]

const TEST_SVC = process.env.NEXT_PUBLIC_TEST_SVC_URL || 'http://localhost:8090'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  model?: string
  trace_id?: string
  feedback?: number        // 0-10, set when submitted
  pendingScore?: number    // selected but not yet submitted
  pendingMessage?: string  // draft text for feedback comment
}

interface Props {
  onClose: () => void
  city?: string
  messages: ChatMessage[]
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  model: string
  setModel: React.Dispatch<React.SetStateAction<string>>
}

export default function ChatModal({ onClose, city, messages, setMessages, model, setModel }: Props) {
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const bottomRef                 = useRef<HTMLDivElement>(null)
  const feedbackInputRef          = useRef<HTMLInputElement>(null)
  const submittingRef             = useRef<Set<number>>(new Set())

  const pendingFeedbackIdx = messages.findIndex(m => m.pendingScore !== undefined && m.feedback === undefined)
  useEffect(() => {
    if (pendingFeedbackIdx !== -1) feedbackInputRef.current?.focus()
  }, [pendingFeedbackIdx])

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
      setMessages(prev => [...prev, { role: 'assistant', content: 'Something went wrong. Please try again.' }])
    } finally {
      setLoading(false)
    }
  }

  const selectScore = (index: number, score: number) => {
    const msg = messages[index]
    if (msg.feedback !== undefined) return
    setMessages(prev => prev.map((m, i) => i === index ? { ...m, pendingScore: score } : m))
  }

  const updatePendingMessage = (index: number, text: string) => {
    setMessages(prev => prev.map((m, i) => i === index ? { ...m, pendingMessage: text } : m))
  }

  const sendFeedback = async (index: number) => {
    const msg = messages[index]
    if (!msg.trace_id || msg.feedback !== undefined || msg.pendingScore === undefined) return
    if (submittingRef.current.has(index)) return  // guard against React state race on double-click

    submittingRef.current.add(index)
    const score = msg.pendingScore
    const message = msg.pendingMessage?.trim() || undefined

    setMessages(prev => prev.map((m, i) =>
      i === index ? { ...m, feedback: score, pendingScore: undefined, pendingMessage: undefined } : m
    ))
    console.info(`[pulse-feed] Chat feedback: score=${score} message="${message || ''}" trace_id=${msg.trace_id}`)

    try {
      await fetch(`${TEST_SVC}/chat/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trace_id: msg.trace_id, rating: score, ...(message ? { message } : {}) }),
      })
    } catch (e) {
      console.error(`[pulse-feed] Chat feedback failed: ${e}`)
    } finally {
      submittingRef.current.delete(index)
    }
  }

  const scoreColor = (score: number) => {
    if (score <= 3) return styles.scoreLow
    if (score <= 6) return styles.scoreMid
    return styles.scoreHigh
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
            {CHAT_MODELS.map(m => (
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
                <>
                  <div className={styles.scoreRow}>
                    {[0,1,2,3,4,5,6,7,8,9,10].map(score => (
                      <button
                        key={score}
                        className={`${styles.scoreBtn} ${scoreColor(score)} ${(m.feedback ?? m.pendingScore) === score ? styles.scoreBtnActive : ''}`}
                        onClick={() => selectScore(i, score)}
                        disabled={m.feedback !== undefined}
                        title={`Rate ${score}/10`}
                      >
                        {score}
                      </button>
                    ))}
                  </div>
                  {m.pendingScore !== undefined && m.feedback === undefined && (
                    <div className={styles.feedbackTextRow}>
                      <input
                        ref={feedbackInputRef}
                        className={styles.feedbackTextInput}
                        value={m.pendingMessage || ''}
                        onChange={e => updatePendingMessage(i, e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); sendFeedback(i) } }}
                        placeholder="Add a comment (optional)..."
                      />
                      <button
                        className={styles.feedbackSubmit}
                        onClick={() => sendFeedback(i)}
                      >
                        SUBMIT
                      </button>
                    </div>
                  )}
                </>
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
