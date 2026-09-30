import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ChatPanel } from '@/components/chat/ChatPanel'
import { Composer } from '@/components/chat/Composer'
import { TopBar } from '@/components/layout/TopBar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { VoiceConsole, type VoiceConsoleRef } from '@/components/voice/VoiceConsole'
import { useTheme } from '@/hooks/useTheme'
import { useUserProfile } from '@/hooks/useUserProfile'
import {
  getAvailableAgents,
  getAvailableModels,
  getRuntimeStatus,
  streamChat,
  syncVoiceTurn,
} from '@/lib/chatApi'
import type {
  AgentCatalogResponse,
  AgentStatus,
  AssistantMessage,
  AssistantWidgetState,
  ChatMessage,
  ModelCatalogResponse,
  RuntimeStatus,
  ServerEvent,
  WidgetPayload,
} from '@/types'

const MODEL_STORAGE_KEY = 'visualizer-agent:selected-model'
const AGENT_STORAGE_KEY = 'visualizer-agent:selected-agent'

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

function sameWidgetPayload(left: WidgetPayload, right: WidgetPayload): boolean {
  return (
    left.title === right.title &&
    left.kind === right.kind &&
    left.widget_code === right.widget_code
  )
}

function findLatestAssistantIndex(messages: ChatMessage[], allowClosed: boolean): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const candidate = messages[index]
    if (candidate?.role !== 'assistant') continue
    if (allowClosed || candidate.isStreaming) return index
  }
  return -1
}

export default function App() {
  const { theme, toggleTheme } = useTheme()
  const { profile, incrementInteraction } = useUserProfile()

  const [conversationId, setConversationId] = useState<string>()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)

  const [agentCatalog, setAgentCatalog] = useState<AgentCatalogResponse | null>(null)
  const [agentCatalogError, setAgentCatalogError] = useState<string | null>(null)
  const [isLoadingAgentCatalog, setIsLoadingAgentCatalog] = useState(false)

  const [modelCatalog, setModelCatalog] = useState<ModelCatalogResponse | null>(null)
  const [modelCatalogError, setModelCatalogError] = useState<string | null>(null)
  const [isLoadingModelCatalog, setIsLoadingModelCatalog] = useState(false)

  const [selectedAgent, setSelectedAgent] = useState('')
  const [selectedModel, setSelectedModel] = useState('')

  const activeAssistantIdRef = useRef<string | null>(null)
  const hasAppliedInitialAgentSelectionRef = useRef(false)
  const activeStreamAbortRef = useRef<AbortController | null>(null)
  const voiceConsoleRef = useRef<VoiceConsoleRef>(null)

  const chatCompatibleModels = useMemo(
    () => modelCatalog?.models.filter((model) => model.chat_compatible) ?? [],
    [modelCatalog],
  )
  const nonChatCompatibleModels = useMemo(
    () => modelCatalog?.models.filter((model) => !model.chat_compatible) ?? [],
    [modelCatalog],
  )
  const availableAgents = useMemo(() => agentCatalog?.agents ?? [], [agentCatalog])

  const loadAgentCatalog = useCallback(async () => {
    setIsLoadingAgentCatalog(true)
    try {
      const result = await getAvailableAgents()
      setAgentCatalog(result)
      setAgentCatalogError(null)
    } catch (catalogError) {
      setAgentCatalogError(
        catalogError instanceof Error ? catalogError.message : 'Could not load available agents.',
      )
    } finally {
      setIsLoadingAgentCatalog(false)
    }
  }, [])

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
    let cancelled = false
    void getRuntimeStatus()
      .then((result) => {
        if (cancelled) return
        setRuntime(result)
        setRuntimeError(null)
        void loadAgentCatalog()
      })
      .catch((runtimeStatusError) => {
        if (cancelled) return
        setRuntimeError(
          runtimeStatusError instanceof Error
            ? runtimeStatusError.message
            : 'Could not load runtime status.',
        )
      })
    return () => { cancelled = true }
  }, [loadAgentCatalog])

  useEffect(() => {
    if (runtime === null) return
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
      if (current && selectableIds.has(current)) return current
      if (storedModel && selectableIds.has(storedModel)) return storedModel
      if (runtime?.model && selectableIds.has(runtime.model)) return runtime.model
      return chatCompatibleModels[0]?.id ?? current
    })
  }, [chatCompatibleModels, runtime?.model])

  useEffect(() => {
    if (availableAgents.length === 0) return
    const selectableIds = new Set(availableAgents.map((agent) => agent.id))
    let storedAgent: string | null = null
    try {
      storedAgent = window.localStorage.getItem(AGENT_STORAGE_KEY)
    } catch {
      storedAgent = null
    }
    setSelectedAgent((current) => {
      if (current && selectableIds.has(current)) return current
      if (storedAgent && selectableIds.has(storedAgent)) return storedAgent
      if (runtime?.defaultAgentId && selectableIds.has(runtime.defaultAgentId)) {
        return runtime.defaultAgentId
      }
      if (agentCatalog?.defaultAgentId && selectableIds.has(agentCatalog.defaultAgentId)) {
        return agentCatalog.defaultAgentId
      }
      return availableAgents[0]?.id ?? current
    })
  }, [agentCatalog?.defaultAgentId, availableAgents, runtime?.defaultAgentId])

  useEffect(() => {
    if (!selectedModel) return
    try {
      window.localStorage.setItem(MODEL_STORAGE_KEY, selectedModel)
    } catch {
      // ignore storage failures
    }
  }, [selectedModel])

  useEffect(() => {
    if (!selectedAgent) return
    try {
      window.localStorage.setItem(AGENT_STORAGE_KEY, selectedAgent)
    } catch {
      // ignore storage failures
    }
  }, [selectedAgent])

  useEffect(() => {
    if (!selectedAgent) return
    if (!hasAppliedInitialAgentSelectionRef.current) {
      hasAppliedInitialAgentSelectionRef.current = true
      return
    }
    // Cancel any in-flight SSE stream so stale deltas don't land in the new conversation.
    if (activeStreamAbortRef.current) {
      activeStreamAbortRef.current.abort()
      activeStreamAbortRef.current = null
    }
    activeAssistantIdRef.current = null
    setIsSending(false)
    setConversationId(undefined)
    setMessages([])
    setError(null)
  }, [selectedAgent])

  const updateLatestAssistant = useCallback(
    (
      updater: (message: AssistantMessage) => AssistantMessage,
      options?: { allowClosed?: boolean; targetId?: string },
    ) => {
      const allowClosed = options?.allowClosed ?? false
      const targetId = options?.targetId
      setMessages((current) => {
        const assistantIndex =
          targetId === undefined
            ? findLatestAssistantIndex(current, allowClosed)
            : current.findIndex(
                (message) => message.role === 'assistant' && message.id === targetId,
              )
        if (assistantIndex < 0) return current
        const next = [...current]
        const target = next[assistantIndex]
        if (target?.role !== 'assistant') return current
        next[assistantIndex] = updater(target)
        return next
      })
    },
    [],
  )

  const ensureAssistantMessage = useCallback(
    (options?: { allowClosed?: boolean; targetId?: string }) => {
      const allowClosed = options?.allowClosed ?? false
      const targetId = options?.targetId
      setMessages((current) => {
        if (targetId !== undefined) {
          const targetIndex = current.findIndex(
            (message) => message.role === 'assistant' && message.id === targetId,
          )
          if (targetIndex >= 0) return current
        }
        const assistantIndex = findLatestAssistantIndex(current, allowClosed)
        if (assistantIndex >= 0) return current
        const assistant = createAssistantMessage()
        if (targetId !== undefined) {
          assistant.id = targetId
        }
        return [...current, assistant]
      })
    },
    [],
  )

  const applyServerEvent = useCallback(
    (event: ServerEvent) => {
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
          typeof event.data?.detail === 'string'
            ? event.data.detail
            : 'The agent is processing your request.'
        const state: AgentStatus['state'] =
          event.data?.state === 'completed' ||
          event.data?.state === 'error' ||
          event.data?.state === 'active'
            ? (event.data.state as AgentStatus['state'])
            : 'active'

        ensureAssistantMessage({ allowClosed: true, targetId: activeAssistantId ?? undefined })
        updateLatestAssistant(
          (message) => ({ ...message, status: { stage, label, detail, state } }),
          { allowClosed: true, targetId: activeAssistantId ?? undefined },
        )
        return
      }

      if (event.type === 'text_delta' && typeof event.data?.text === 'string') {
        const text = event.data.text
        ensureAssistantMessage({ targetId: activeAssistantId ?? undefined })
        updateLatestAssistant(
          (message) => ({ ...message, answerText: message.answerText + text }),
          { targetId: activeAssistantId ?? undefined },
        )
        return
      }

      if (event.type === 'thinking_delta' && typeof event.data?.text === 'string') {
        const text = event.data.text
        ensureAssistantMessage({ targetId: activeAssistantId ?? undefined })
        updateLatestAssistant(
          (message) => ({ ...message, thinkingText: message.thinkingText + text }),
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
            return { ...message, widgets }
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
            if (
              message.widgets.some(
                (widgetState) =>
                  widgetState.widget &&
                  !widgetState.errorMessage &&
                  sameWidgetPayload(widgetState.widget, widget),
              )
            ) {
              return message
            }
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
    },
    [ensureAssistantMessage, updateLatestAssistant],
  )

  const sendMessage = useCallback(
    async (text: string, options?: { from_widget?: string }) => {
      const value = text.trim()
      if (!value || isSending || runtime?.ready === false) return

      if (voiceConsoleRef.current?.isConnected) {
        let liveText = value
        if (options?.from_widget) {
          liveText = `I just clicked on the hyperlink "${value}" in the visual "${options.from_widget}". Please generate a new visual for this and explain it.`
        }
        const sent = voiceConsoleRef.current.sendText(liveText)
        if (sent) {
          setInput('')
        }
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

      const abortController = new AbortController()
      activeStreamAbortRef.current = abortController
      try {
        incrementInteraction()
        await streamChat(
          {
            conversation_id: conversationId,
            message: value,
            agent_id: selectedAgent || undefined,
            user_profile: profile,
            model: selectedModel || undefined,
            from_widget: options?.from_widget,
          },
          applyServerEvent,
          { signal: abortController.signal },
        )
      } catch (streamError) {
        if (abortController.signal.aborted) {
          // Cancellation is expected (e.g., agent switch); state was reset by the caller.
          return
        }
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
          { allowClosed: true, targetId: assistantId },
        )
      } finally {
        if (activeStreamAbortRef.current === abortController) {
          activeStreamAbortRef.current = null
        }
      }
    },
    [
      applyServerEvent,
      conversationId,
      isSending,
      runtime?.ready,
      selectedAgent,
      selectedModel,
      updateLatestAssistant,
    ],
  )

  const getLatestWidgetTitle = (message: AssistantMessage): string | null => {
    for (let index = message.widgets.length - 1; index >= 0; index -= 1) {
      const widgetState = message.widgets[index]
      if (widgetState?.widget !== null) {
        return widgetState.widget.title
      }
    }
    return null
  }

  const sendFollowUpMessage = useCallback(
    async (chip: string, messageId: string) => {
      const sourceMessage = messages.find(
        (message): message is AssistantMessage =>
          message.id === messageId && message.role === 'assistant',
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
    },
    [messages, sendMessage],
  )

  const startDelegatedTurn = useCallback((text: string) => {
    const value = text.trim()
    if (!value) return
    const assistantId = crypto.randomUUID()
    activeAssistantIdRef.current = assistantId
    setError(null)
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', text: value },
      {
        ...createAssistantMessage(),
        id: assistantId,
        status: {
          stage: 'delegated',
          label: 'Delegated from voice',
          detail: 'The live dialogue agent forwarded this request into the backend visual chat.',
          state: 'active',
        },
      },
    ])
  }, [])

  const handleTranscriptTurnComplete = useCallback(
    async (userText: string, assistantText: string) => {
      const uText = userText.trim()
      const aText = assistantText.trim()
      if (!uText && !aText) return

      const newMessages: ChatMessage[] = []
      if (uText) {
        newMessages.push({ id: crypto.randomUUID(), role: 'user', text: uText })
      }
      if (aText) {
        const assistantMessage = createAssistantMessage()
        assistantMessage.answerText = aText
        assistantMessage.isStreaming = false
        assistantMessage.status = {
          stage: 'completed',
          label: 'Completed',
          detail: 'Voice transcript saved.',
          state: 'completed',
        }
        newMessages.push(assistantMessage)
      }

      setMessages((current) => [...current, ...newMessages])

      try {
        const result = await syncVoiceTurn({
          conversation_id: conversationId || undefined,
          user_text: uText,
          assistant_text: aText,
        })
        if (!conversationId && result.conversation_id) {
          setConversationId(result.conversation_id)
        }
      } catch (err) {
        console.error('Failed to sync voice turn', err)
      }
    },
    [conversationId],
  )

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex min-h-screen flex-col bg-background text-foreground">
        <TopBar
          runtime={runtime}
          runtimeError={runtimeError}
          conversationId={conversationId}
          agentCatalog={agentCatalog}
          agentCatalogError={agentCatalogError}
          isLoadingAgentCatalog={isLoadingAgentCatalog}
          selectedAgent={selectedAgent}
          onSelectAgent={setSelectedAgent}
          onReloadAgents={() => void loadAgentCatalog()}
          modelCatalog={modelCatalog}
          modelCatalogError={modelCatalogError}
          isLoadingModelCatalog={isLoadingModelCatalog}
          chatCompatibleModels={chatCompatibleModels}
          nonChatCompatibleModels={nonChatCompatibleModels}
          selectedModel={selectedModel}
          onSelectModel={setSelectedModel}
          onReloadModels={() => void loadModelCatalog()}
          theme={theme}
          onToggleTheme={toggleTheme}
        />

        <div className="w-full px-4 pt-4 md:px-8">
          <VoiceConsole
            ref={voiceConsoleRef}
            runtime={runtime}
            selectedAgent={selectedAgent}
            selectedModel={selectedModel}
            conversationId={conversationId}
            onDelegatedTurnStart={startDelegatedTurn}
            onDelegatedServerEvent={applyServerEvent}
            onTranscriptTurnComplete={handleTranscriptTurnComplete}
          />
        </div>

        <main className="flex w-full flex-1 flex-col">
          <ChatPanel
            messages={messages}
            isSending={isSending}
            selectedAgent={selectedAgent}
            runtimeReady={runtime?.ready === true}
            onSendMessage={(text, options) => void sendMessage(text, options)}
            onSendFollowUp={(chip, messageId) => void sendFollowUpMessage(chip, messageId)}
          />
          <Composer
            value={input}
            onChange={setInput}
            onSubmit={() => void sendMessage(input)}
            disabled={isSending || runtime?.ready === false}
            isSending={isSending}
            error={error}
            placeholder={
              selectedAgent === 'svg'
                ? 'Ask for template selection, slot mapping, SVG validation, or brand-safe SVG edits.'
                : 'Explain a concept, compare two ideas, or ask for a visual walkthrough.'
            }
          />
        </main>
      </div>
    </TooltipProvider>
  )
}
