import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'

import './App.css'
import { WidgetFrame } from './components/WidgetFrame'
import { getAvailableModels, getRuntimeStatus, streamChat } from './lib/chatApi'
import type {
  AvailableModel,
  AgentStatus,
  AssistantMessage,
  AssistantWidgetState,
  ChatMessage,
  ModelCatalogResponse,
  RuntimeStatus,
  ServerEvent,
  WidgetPayload,
} from './types'

const MODEL_STORAGE_KEY = 'visualizer-agent:selected-model'

function createAssistantMessage(): AssistantMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    thinkingText: '',
    answerText: '',
    widgets: [],
    followUp: null,
    isStreaming: true,
    status: null,
  }
}

function createWidgetState(loadingMessages: string[]): AssistantWidgetState {
  return {
    id: crypto.randomUUID(),
    widget: null,
    loadingMessages,
    isLoading: true,
    errorMessage: null,
  }
}

function AssistantText({ text, isStreaming }: { text: string; isStreaming: boolean }) {
  const markdown = useMemo(
    () => (
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
        {text}
      </ReactMarkdown>
    ),
    [text],
  )

  if (isStreaming) {
    return <div className="streaming-text">{text}</div>
  }

  return <div className="markdown-body">{markdown}</div>
}

function ReasoningCard({ text, isStreaming }: { text: string; isStreaming: boolean }) {
  const [isOpenAfterStreaming, setIsOpenAfterStreaming] = useState(false)
  const tokenEstimate = Math.max(1, Math.round(text.length / 4))
  const open = isStreaming ? true : isOpenAfterStreaming

  return (
    <details
      className="reasoning-card"
      open={open}
      onToggle={(event) => {
        if (!isStreaming) {
          setIsOpenAfterStreaming(event.currentTarget.open)
        }
      }}
    >
      <summary className="reasoning-summary">
        <span>Reasoning</span>
        <span>{isStreaming ? 'Streaming…' : `${tokenEstimate} thinking tokens`}</span>
      </summary>
      <div className="reasoning-body">{text}</div>
    </details>
  )
}

function LoadingCard({ messages }: { messages: string[] }) {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % messages.length)
    }, 1800)
    return () => window.clearInterval(timer)
  }, [messages])

  return (
    <div
      className="widget-loading-card"
      role="status"
      aria-live="polite"
      aria-label="Visual loading"
    >
      <div className="loading-spinner" aria-hidden="true" />
      <div className="loading-copy">
        <div className="loading-title">Building the visualization</div>
        <div className="loading-message">{messages[index]}</div>
      </div>
    </div>
  )
}

function WidgetErrorCard({ message }: { message: string }) {
  return (
    <div className="widget-error-card" role="status" aria-live="polite">
      <div className="widget-error-title">Visual unavailable</div>
      <div className="widget-error-copy">{message}</div>
    </div>
  )
}

function StatusPill({ status }: { status: AgentStatus }) {
  return (
    <div className={`status-pill status-${status.state}`}>
      <div className="status-pill-label">{status.label}</div>
      <div className="status-pill-detail">{status.detail}</div>
    </div>
  )
}

function findLatestAssistantIndex(messages: ChatMessage[], allowClosed: boolean): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const candidate = messages[index]
    if (candidate?.role !== 'assistant') {
      continue
    }
    if (allowClosed || candidate.isStreaming) {
      return index
    }
  }
  return -1
}

function getLatestWidgetTitle(message: AssistantMessage): string | null {
  for (let index = message.widgets.length - 1; index >= 0; index -= 1) {
    const widgetState = message.widgets[index]
    if (widgetState?.widget !== null) {
      return widgetState.widget.title
    }
  }
  return null
}

function buildModelOptionLabel(model: AvailableModel): string {
  return model.display_name === model.id ? model.display_name : `${model.display_name} (${model.id})`
}

function App() {
  const [conversationId, setConversationId] = useState<string>()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [modelCatalog, setModelCatalog] = useState<ModelCatalogResponse | null>(null)
  const [modelCatalogError, setModelCatalogError] = useState<string | null>(null)
  const [isLoadingModelCatalog, setIsLoadingModelCatalog] = useState(false)
  const [selectedModel, setSelectedModel] = useState('')
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const activeAssistantIdRef = useRef<string | null>(null)

  const chatCompatibleModels = useMemo(
    () => modelCatalog?.models.filter((model) => model.chat_compatible) ?? [],
    [modelCatalog],
  )
  const nonChatCompatibleModels = useMemo(
    () => modelCatalog?.models.filter((model) => !model.chat_compatible) ?? [],
    [modelCatalog],
  )
  const displayedModel = selectedModel || runtime?.model || 'gemini-3.1-flash-lite-preview'

  const loadModelCatalog = useCallback(async () => {
    setIsLoadingModelCatalog(true)
    try {
      const result = await getAvailableModels()
      setModelCatalog(result)
      setModelCatalogError(null)
    } catch (catalogError) {
      setModelCatalogError(
        catalogError instanceof Error ? catalogError.message : 'Could not load available models.',
      )
    } finally {
      setIsLoadingModelCatalog(false)
    }
  }, [])

  useEffect(() => {
    void getRuntimeStatus()
      .then((result) => {
        setRuntime(result)
        setRuntimeError(null)
      })
      .catch((runtimeStatusError) => {
        setRuntimeError(
          runtimeStatusError instanceof Error ? runtimeStatusError.message : 'Could not load runtime status.',
        )
      })
  }, [])

  useEffect(() => {
    if (runtime === null) {
      return
    }
    if (!runtime.ready) {
      setModelCatalog(null)
      setModelCatalogError(null)
      setIsLoadingModelCatalog(false)
      return
    }
    void loadModelCatalog()
  }, [loadModelCatalog, runtime])

  useEffect(() => {
    if (chatCompatibleModels.length === 0) {
      setSelectedModel('')
      return
    }
    const selectableIds = new Set(chatCompatibleModels.map((model) => model.id))
    let storedModel: string | null = null
    try {
      storedModel = window.localStorage.getItem(MODEL_STORAGE_KEY)
    } catch {
      storedModel = null
    }
    setSelectedModel((current) => {
      if (current && selectableIds.has(current)) {
        return current
      }
      if (storedModel && selectableIds.has(storedModel)) {
        return storedModel
      }
      if (runtime?.model && selectableIds.has(runtime.model)) {
        return runtime.model
      }
      return chatCompatibleModels[0]?.id ?? current
    })
  }, [chatCompatibleModels, runtime?.model])

  useEffect(() => {
    if (!selectedModel) {
      return
    }
    try {
      window.localStorage.setItem(MODEL_STORAGE_KEY, selectedModel)
    } catch {
      // Ignore storage failures; selection still lives in memory for this session.
    }
  }, [selectedModel])

  useEffect(() => {
    viewportRef.current?.scrollTo({
      top: viewportRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages])

  const updateLatestAssistant = (
    updater: (message: AssistantMessage) => AssistantMessage,
    options?: { allowClosed?: boolean; targetId?: string },
  ) => {
    const allowClosed = options?.allowClosed ?? false
    const targetId = options?.targetId
    setMessages((current) => {
      const assistantIndex =
        targetId === undefined
          ? findLatestAssistantIndex(current, allowClosed)
          : current.findIndex((message) => message.role === 'assistant' && message.id === targetId)
      if (assistantIndex < 0) {
        return current
      }
      const next = [...current]
      const target = next[assistantIndex]
      if (target?.role !== 'assistant') {
        return current
      }
      next[assistantIndex] = updater(target)
      return next
    })
  }

  const ensureAssistantMessage = (options?: { allowClosed?: boolean; targetId?: string }) => {
    const allowClosed = options?.allowClosed ?? false
    const targetId = options?.targetId
    setMessages((current) => {
      if (targetId !== undefined) {
        const targetIndex = current.findIndex(
          (message) => message.role === 'assistant' && message.id === targetId,
        )
        if (targetIndex >= 0) {
          return current
        }
      }
      const assistantIndex = findLatestAssistantIndex(current, allowClosed)
      if (assistantIndex >= 0) {
        return current
      }
      const assistant = createAssistantMessage()
      if (targetId !== undefined) {
        assistant.id = targetId
      }
      return [...current, assistant]
    })
  }

  const applyServerEvent = (event: ServerEvent) => {
    const activeAssistantId = activeAssistantIdRef.current

    if (event.type === 'conversation' && typeof event.data?.conversationId === 'string') {
      setConversationId(event.data.conversationId)
      return
    }

    if (event.type === 'assistant_started') {
      ensureAssistantMessage({ targetId: activeAssistantId ?? undefined })
      return
    }

    if (event.type === 'status') {
      const stage = typeof event.data?.stage === 'string' ? event.data.stage : 'working'
      const label = typeof event.data?.label === 'string' ? event.data.label : 'Working'
      const detail =
        typeof event.data?.detail === 'string' ? event.data.detail : 'The agent is processing your request.'
      const state =
        event.data?.state === 'completed' || event.data?.state === 'error' || event.data?.state === 'active'
          ? event.data.state
          : 'active'

      ensureAssistantMessage({ allowClosed: true, targetId: activeAssistantId ?? undefined })
      updateLatestAssistant(
        (message) => ({
          ...message,
          status: {
            stage,
            label,
            detail,
            state,
          },
        }),
        { allowClosed: true, targetId: activeAssistantId ?? undefined },
      )
      return
    }

    if (event.type === 'text_delta' && typeof event.data?.text === 'string') {
      const text = event.data.text
      ensureAssistantMessage({ targetId: activeAssistantId ?? undefined })
      updateLatestAssistant(
        (message) => ({
          ...message,
          answerText: message.answerText + text,
        }),
        { targetId: activeAssistantId ?? undefined },
      )
      return
    }

    if (event.type === 'thinking_delta' && typeof event.data?.text === 'string') {
      const text = event.data.text
      ensureAssistantMessage({ targetId: activeAssistantId ?? undefined })
      updateLatestAssistant(
        (message) => ({
          ...message,
          thinkingText: message.thinkingText + text,
        }),
        { targetId: activeAssistantId ?? undefined },
      )
      return
    }

    if (event.type === 'widget_loading') {
      ensureAssistantMessage({ targetId: activeAssistantId ?? undefined })
      const loadingMessages = Array.isArray(event.data?.loadingMessages)
        ? event.data.loadingMessages.filter((item): item is string => typeof item === 'string')
        : ['Building the visualization…']
      updateLatestAssistant(
        (message) => {
          const widgets = [...message.widgets]
          const lastWidget = widgets[widgets.length - 1]
          if (lastWidget && lastWidget.widget === null) {
            widgets[widgets.length - 1] = {
              ...lastWidget,
              isLoading: true,
              loadingMessages,
              errorMessage: null,
            }
          } else {
            widgets.push(createWidgetState(loadingMessages))
          }
          return {
            ...message,
            widgets,
          }
        },
        { targetId: activeAssistantId ?? undefined },
      )
      return
    }

    if (event.type === 'widget_ready' && event.data?.widget) {
      const widget = event.data.widget as WidgetPayload
      ensureAssistantMessage({ targetId: activeAssistantId ?? undefined })
      updateLatestAssistant(
        (message) => {
          const widgets = [...message.widgets]
          const pendingIndex = [...widgets].reverse().findIndex((item) => item.widget === null)

          if (pendingIndex >= 0) {
            const targetIndex = widgets.length - 1 - pendingIndex
            widgets[targetIndex] = {
              ...widgets[targetIndex],
              widget,
              isLoading: false,
              loadingMessages: widget.loading_messages,
              errorMessage: null,
            }
          } else {
            widgets.push({
              id: crypto.randomUUID(),
              widget,
              loadingMessages: widget.loading_messages,
              isLoading: false,
              errorMessage: null,
            })
          }

          return { ...message, widgets }
        },
        { targetId: activeAssistantId ?? undefined },
      )
      return
    }

    if (event.type === 'assistant_done') {
      updateLatestAssistant(
        (message) => ({
          ...message,
          isStreaming: false,
          status:
            message.status?.state === 'error'
              ? message.status
              : message.status === null
                ? {
                    stage: 'completed',
                    label: 'Completed',
                    detail: 'The answer is ready.',
                    state: 'completed',
                  }
                : {
                    ...message.status,
                    stage: 'completed',
                    label: 'Completed',
                    detail: 'The answer is ready.',
                    state: 'completed',
                  },
          followUp: {
            chips: Array.isArray(event.data?.followUpChips)
              ? event.data.followUpChips.filter((item): item is string => typeof item === 'string')
              : [],
          },
        }),
        { targetId: activeAssistantId ?? undefined },
      )
      return
    }

    if (event.type === 'error' && typeof event.data?.detail === 'string') {
      const detailsObj =
        typeof event.data?.details === 'object' && event.data?.details !== null
          ? (event.data.details as Record<string, unknown>)
          : null
      const retryAfterSeconds =
        detailsObj && typeof detailsObj.retry_after_seconds === 'number'
          ? detailsObj.retry_after_seconds
          : null
      const detail =
        typeof retryAfterSeconds === 'number' && event.data?.title === 'RATE_LIMITED'
          ? `${event.data.detail} — retry in about ${retryAfterSeconds}s.`
          : event.data.detail
      const errTitle = typeof event.data?.title === 'string' ? event.data.title : ''
      const widgetLoadingNote =
        errTitle === 'VISUAL_NOT_PRODUCED'
          ? 'No diagram this turn. The visual generation step failed or was cut off.'
          : 'Failed to load widget.'

      setError(detail)
      setIsSending(false)
      activeAssistantIdRef.current = null
      updateLatestAssistant(
        (message) => ({
          ...message,
          isStreaming: false,
          widgets: message.widgets.map((widgetState) =>
            widgetState.widget === null
              ? {
                  ...widgetState,
                  isLoading: false,
                  errorMessage: widgetLoadingNote,
                  loadingMessages: [widgetLoadingNote],
                }
              : widgetState,
          ),
          status: {
            stage: 'failed',
            label: 'Needs attention',
            detail,
            state: 'error',
          },
        }),
        { allowClosed: true, targetId: activeAssistantId ?? undefined },
      )
      return
    }

    if (event.type === 'done') {
      setIsSending(false)
      activeAssistantIdRef.current = null
    }
  }

  const sendMessage = async (text: string, options?: { from_widget?: string }) => {
    const value = text.trim()
    if (!value || isSending || runtime?.ready === false) {
      return
    }

    setError(null)
    setInput('')
    setIsSending(true)
    const assistantId = crypto.randomUUID()
    activeAssistantIdRef.current = assistantId
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', text: value },
      {
        ...createAssistantMessage(),
        id: assistantId,
        status: {
          stage: 'queued',
          label: 'Queued',
          detail: 'The request is on its way to the backend.',
          state: 'active',
        },
      },
    ])

    try {
      await streamChat(
        {
          conversation_id: conversationId,
          message: value,
          model: selectedModel || undefined,
          from_widget: options?.from_widget,
        },
        applyServerEvent,
      )
    } catch (streamError) {
      setIsSending(false)
      activeAssistantIdRef.current = null
      setError(streamError instanceof Error ? streamError.message : 'Something went wrong.')
      updateLatestAssistant(
        (message) => ({
          ...message,
          isStreaming: false,
          widgets: message.widgets.map((widgetState) =>
            widgetState.widget === null
              ? {
                  ...widgetState,
                  isLoading: false,
                  errorMessage: 'Failed to load widget.',
                  loadingMessages: ['Failed to load widget.'],
                }
              : widgetState,
          ),
        }),
        {
          allowClosed: true,
          targetId: assistantId,
        },
      )
    }
  }

  const sendFollowUpMessage = async (chip: string, messageId: string) => {
    const sourceMessage = messages.find(
      (message): message is AssistantMessage => message.id === messageId && message.role === 'assistant',
    )
    const widgetTitle = sourceMessage ? getLatestWidgetTitle(sourceMessage) : null

    setMessages((current) =>
      current.map((message) =>
        message.id === messageId && message.role === 'assistant'
          ? { ...message, followUp: null }
          : message,
      ),
    )
    await sendMessage(chip, widgetTitle ? { from_widget: widgetTitle } : undefined)
  }

  const onSubmit = async (event: { preventDefault(): void }) => {
    event.preventDefault()
    await sendMessage(input)
  }

  return (
    <main className="app-shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow">PydanticAI + Gemini visual agent</span>
          <h1>Ask naturally. Learn visually. Stay in the same chat.</h1>
          <p>
            This proof of concept composes each turn into a reasoning panel, a main answer card,
            and a final visuals section instead of mirroring raw tool-call order.
          </p>
        </div>
        <div className="hero-meta">
          <div className="meta-card">
            <span>Model</span>
            <strong>{displayedModel}</strong>
          </div>
          <div className="meta-card">
            <span>Frontend</span>
            <strong>Bun + React</strong>
          </div>
          <div className="meta-card">
            <span>Backend</span>
            <strong>FastAPI + PydanticAI</strong>
          </div>
        </div>
      </section>

      <section className="chat-panel">
        <div className="chat-toolbar">
          <div>
            <h2>Visual learning chat</h2>
            <p>Try: “Compare dense vs MoE visually with one final diagram.”</p>
          </div>
          <div className="conversation-badge">{conversationId ?? 'New conversation'}</div>
        </div>

        <div className="runtime-strip">
          <div className={`runtime-state ${runtime?.ready ? 'runtime-ready' : 'runtime-warn'}`}>
            {runtime?.ready ? 'Agent ready' : 'Agent not ready'}
          </div>
          <div className="runtime-copy">
            {runtimeError ? (
              runtimeError
            ) : runtime?.ready ? (
              `Expect: receive → think → stream answer → finalize visual section → save conversation${
                runtime.fallbackModel ? ` • fallback: ${runtime.fallbackModel}` : ''
              }`
            ) : (
              `Set GOOGLE_API_KEY in ${runtime?.envSources.join(' or ') ?? 'the environment'} and reload.`
            )}
          </div>
          {runtime ? (
            <div className="runtime-limits">
              <span>RPM {runtime.limits.requestsPerMinute}</span>
              <span>TPM {runtime.limits.tokensPerMinute.toLocaleString()}</span>
              <span>RPD {runtime.limits.requestsPerDay}</span>
            </div>
          ) : null}
        </div>

        <div className="chat-viewport" ref={viewportRef}>
          {messages.length === 0 ? (
            <div className="empty-state">
              <h3>Start with a concept, mechanism, or comparison.</h3>
              <div className="chip-row">
                {[
                  'Explain gradient descent visually',
                  'Compare stack vs queue',
                  'Compare dense vs MoE visually',
                ].map((suggestion) => (
                  <button key={suggestion} className="chip" onClick={() => void sendMessage(suggestion)}>
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {messages.map((message) =>
            message.role === 'user' ? (
              <article key={message.id} className="message user-message">
                <div className="message-label">You</div>
                <div className="message-surface">{message.text}</div>
              </article>
            ) : (
              <article key={message.id} className="message assistant-message">
                <div className="message-label">Agent</div>
                <div className="assistant-stack">
                  {message.status ? <StatusPill status={message.status} /> : null}

                  {message.thinkingText ? (
                    <div className="reasoning-shell">
                      <ReasoningCard text={message.thinkingText} isStreaming={message.isStreaming} />
                    </div>
                  ) : null}
                  {!message.isStreaming &&
                  !message.thinkingText &&
                  (message.answerText || message.widgets.length > 0) ? (
                    <div className="reasoning-note">
                      This model did not return visible reasoning tokens for this turn.
                    </div>
                  ) : null}

                  {message.answerText ? (
                    <div className="message-surface assistant-answer-surface">
                      <AssistantText text={message.answerText} isStreaming={message.isStreaming} />
                    </div>
                  ) : null}

                  {message.widgets.length > 0 ? (
                    <section className="visuals-panel" aria-label="Final visuals">
                      <div className="visuals-panel-header">Visuals</div>
                      <div className="visuals-panel-body">
                        {message.widgets.map((widgetState) => (
                          <div key={widgetState.id} className="widget-shell">
                            {widgetState.widget ? (
                              <WidgetFrame
                                widget={widgetState.widget}
                                onPrompt={(text) =>
                                  void sendMessage(text, { from_widget: widgetState.widget!.title })
                                }
                              />
                            ) : widgetState.errorMessage ? (
                              <WidgetErrorCard message={widgetState.errorMessage} />
                            ) : (
                              <LoadingCard
                                key={widgetState.loadingMessages.join('|')}
                                messages={widgetState.loadingMessages}
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  {message.followUp?.chips.length ? (
                    <div className="chip-row" aria-label="Follow-up suggestions">
                      {message.followUp.chips.map((chip) => (
                        <button
                          key={chip}
                          className="chip"
                          onClick={() => void sendFollowUpMessage(chip, message.id)}
                        >
                          {chip}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </article>
            ),
          )}
        </div>

        <form className="composer" onSubmit={onSubmit}>
          <div className="model-picker">
            <label className="composer-label" htmlFor="model-picker">
              Model
            </label>
            <div className="model-picker-row">
              <select
                id="model-picker"
                value={selectedModel}
                onChange={(event) => setSelectedModel(event.target.value)}
                disabled={runtime?.ready === false || isLoadingModelCatalog || chatCompatibleModels.length === 0}
              >
                {chatCompatibleModels.length === 0 ? (
                  <option value="">
                    {runtime?.ready === false
                      ? 'Set a Gemini API key to load models'
                      : isLoadingModelCatalog
                        ? 'Loading models from Gemini…'
                        : 'No selectable Gemini models found'}
                  </option>
                ) : null}
                {chatCompatibleModels.length > 0 ? (
                  <optgroup label="Selectable for this chat">
                    {chatCompatibleModels.map((model) => (
                      <option key={model.id} value={model.id}>
                        {buildModelOptionLabel(model)}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
                {nonChatCompatibleModels.length > 0 ? (
                  <optgroup label="Visible on this key, disabled here">
                    {nonChatCompatibleModels.map((model) => (
                      <option key={model.id} value={model.id} disabled>
                        {buildModelOptionLabel(model)}
                      </option>
                    ))}
                  </optgroup>
                ) : null}
              </select>
              <button
                type="button"
                className="secondary-button"
                onClick={() => void loadModelCatalog()}
                disabled={runtime?.ready === false || isSending || isLoadingModelCatalog}
              >
                {isLoadingModelCatalog ? 'Refreshing…' : 'Refresh models'}
              </button>
            </div>
            <p className={modelCatalogError ? 'error-text' : 'model-picker-help'}>
              {modelCatalogError
                ? modelCatalogError
                : runtime?.ready === false
                  ? 'The picker loads from the backend once a Gemini API key is available.'
                  : modelCatalog
                    ? `${modelCatalog.models.length} models are visible on this API key. ${chatCompatibleModels.length} support generateContent and are selectable for this chat flow. Default: ${modelCatalog.defaultModel}.`
                    : 'The model picker is loading the Gemini catalog for this API key.'}
            </p>
          </div>
          <label className="composer-label" htmlFor="chat-input">
            Prompt
          </label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Explain a concept, compare two ideas, or ask for a visual walkthrough."
            rows={4}
            disabled={isSending || runtime?.ready === false}
          />
          <div className="composer-footer">
            {error ? <p className="error-text">{error}</p> : <p>Visuals render inside a sandboxed iframe.</p>}
            <button
              type="submit"
              className="composer-submit"
              disabled={isSending || !input.trim() || runtime?.ready === false}
            >
              {isSending ? 'Thinking…' : 'Send'}
            </button>
          </div>
        </form>
      </section>
    </main>
  )
}

export default App
