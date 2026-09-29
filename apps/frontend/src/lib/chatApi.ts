import type {
  AgentCatalogResponse,
  ChatRequest,
  ModelCatalogResponse,
  RuntimeStatus,
  ServerEvent,
} from '../types'

function resolveApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL
  if (configured) return configured
  if (typeof window !== 'undefined') return window.location.origin
  return 'http://localhost:8000'
}

const apiBaseUrl = resolveApiBaseUrl()
const chatApiKey = import.meta.env.VITE_CHAT_API_KEY as string | undefined
const DEFAULT_TIMEOUT = 30000 // 30 seconds

// Simple rate limiter to prevent API spamming
class RateLimiter {
  private lastRequest: number = 0
  private minInterval: number

  constructor(minInterval: number = 1000) {
    this.minInterval = minInterval
  }

  async waitForAvailability(): Promise<void> {
    const now = Date.now()
    // Reserve the next slot up front so concurrent callers queue behind each
    // other instead of all firing at once.
    const scheduled = Math.max(now, this.lastRequest + this.minInterval)
    this.lastRequest = scheduled
    const wait = scheduled - now
    if (wait > 0) {
      await new Promise((resolve) => setTimeout(resolve, wait))
    }
  }
}

const chatRateLimiter = new RateLimiter(1000) // 1 second between chat requests
const generalRateLimiter = new RateLimiter(200) // 200ms between general requests

function createTimeoutController(timeoutMs: number = DEFAULT_TIMEOUT): {
  controller: AbortController
  cleanup: () => void
} {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  
  const cleanup = () => {
    clearTimeout(timeoutId)
  }
  
  return { controller, cleanup }
}

function parseSseChunk(chunk: string): ServerEvent[] {
  const events: ServerEvent[] = []
  const frames = chunk.split('\n\n')

  for (const frame of frames) {
    if (!frame.trim()) {
      continue
    }
    const dataLines = frame
      .split('\n')
      .map((line) => line.trimEnd())
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())

    if (dataLines.length === 0) {
      continue
    }

    const payload = dataLines.join('\n')
    if (payload === '[DONE]') {
      events.push({ type: 'done', data: {} })
      continue
    }
    try {
      events.push(JSON.parse(payload) as ServerEvent)
    } catch {
      continue
    }
  }

  return events
}

export async function streamChat(
  payload: ChatRequest,
  onEvent: (event: ServerEvent) => void,
  options?: { signal?: AbortSignal },
): Promise<void> {
  // Apply rate limiting
  await chatRateLimiter.waitForAvailability()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (chatApiKey) {
    headers.Authorization = `Bearer ${chatApiKey}`
  }

  const signal = options?.signal
  const { controller: timeoutController, cleanup: timeoutCleanup } = createTimeoutController()
  
  // Combine user-provided signal with timeout signal
  const combinedSignal = signal ? AbortSignal.any([signal, timeoutController.signal]) : timeoutController.signal

  const response = await fetch(`${apiBaseUrl}/api/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal: combinedSignal,
  }).finally(timeoutCleanup)

  if (!response.ok || response.body === null) {
    const errorText = await response.text()
    throw new Error(errorText || `Request failed with ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const abortHandler = () => {
    void reader.cancel().catch(() => {
      // Ignore cancellation errors.
    })
  }
  if (combinedSignal) {
    if (combinedSignal.aborted) {
      abortHandler()
    } else {
      combinedSignal.addEventListener('abort', abortHandler, { once: true })
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        for (const event of parseSseChunk(`${part}\n\n`)) {
          onEvent(event)
        }
      }
    }

    buffer += decoder.decode()
    buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

    if (buffer.trim()) {
      for (const event of parseSseChunk(buffer)) {
        onEvent(event)
      }
    }
  } finally {
    if (combinedSignal) {
      combinedSignal.removeEventListener('abort', abortHandler)
    }
  }
}

export async function syncVoiceTurn(
  payload: {
    conversation_id?: string
    user_text: string
    assistant_text: string
  }
): Promise<{ conversation_id: string }> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (chatApiKey) {
    headers.Authorization = `Bearer ${chatApiKey}`
  }

  const { controller: timeoutController, cleanup: timeoutCleanup } = createTimeoutController(15000) // 15s timeout for sync

  const url = `${apiBaseUrl}/api/chat/sync_voice`
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal: timeoutController.signal,
  }).finally(timeoutCleanup)

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(errorData.detail || `Server error: ${response.status}`)
  }
  const data = await response.json()
  return { conversation_id: data.conversation_id }
}

export async function getRuntimeStatus(): Promise<RuntimeStatus> {
  await generalRateLimiter.waitForAvailability()
  const { controller: timeoutController, cleanup: timeoutCleanup } = createTimeoutController(10000) // 10s timeout
  const response = await fetch(`${apiBaseUrl}/api/runtime`, {
    signal: timeoutController.signal,
  }).finally(timeoutCleanup)
  if (!response.ok) {
    throw new Error(`Runtime check failed with ${response.status}`)
  }
  return (await response.json()) as RuntimeStatus
}

export async function getAvailableModels(): Promise<ModelCatalogResponse> {
  await generalRateLimiter.waitForAvailability()
  const { controller: timeoutController, cleanup: timeoutCleanup } = createTimeoutController(10000) // 10s timeout
  const response = await fetch(`${apiBaseUrl}/api/models`, {
    signal: timeoutController.signal,
  }).finally(timeoutCleanup)
  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || `Model catalog request failed with ${response.status}`)
  }
  return (await response.json()) as ModelCatalogResponse
}

export async function getAvailableAgents(): Promise<AgentCatalogResponse> {
  await generalRateLimiter.waitForAvailability()
  const { controller: timeoutController, cleanup: timeoutCleanup } = createTimeoutController(10000) // 10s timeout
  const response = await fetch(`${apiBaseUrl}/api/agents`, {
    signal: timeoutController.signal,
  }).finally(timeoutCleanup)
  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || `Agent catalog request failed with ${response.status}`)
  }
  return (await response.json()) as AgentCatalogResponse
}
