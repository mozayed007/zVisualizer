export type WidgetKind = 'svg' | 'html'

export interface WidgetPayload {
  title: string
  loading_messages: string[]
  widget_code: string
  kind: WidgetKind
}

export interface FollowUpState {
  chips: string[]
}

export interface AssistantWidgetState {
  id: string
  widget: WidgetPayload | null
  loadingMessages: string[]
  isLoading: boolean
  errorMessage: string | null
}

export interface UserMessage {
  id: string
  role: 'user'
  text: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  thinkingText: string
  answerText: string
  widgets: AssistantWidgetState[]
  followUp: FollowUpState | null
  isStreaming: boolean
  status: AgentStatus | null
}

export type ChatMessage = UserMessage | AssistantMessage

export interface ChatRequest {
  conversation_id?: string
  message: string
  subject?: string
  agent_id?: string
  model?: string
  from_widget?: string
}

export interface ServerEvent {
  type: string
  data?: Record<string, unknown>
}

export interface AgentStatus {
  stage: string
  label: string
  detail: string
  state: 'active' | 'completed' | 'error'
}

export interface RuntimeStatus {
  ready: boolean
  environment: string
  defaultAgentId: string
  defaultAgentName: string
  model: string
  configuredModel?: string
  fallbackModel?: string | null
  limits: {
    requestsPerMinute: number
    tokensPerMinute: number
    requestsPerDay: number
    maxInputTokens: number
    reservedOutputTokens: number
    maxHistoryTokens: number
  }
  live: {
    ready: boolean
    model: string
    voice: string
    inputAudioMimeType: string
    outputAudioMimeType: string
  }
  envSources: string[]
}

export interface AvailableModel {
  id: string
  resource_name: string
  display_name: string
  description?: string | null
  input_token_limit?: number | null
  output_token_limit?: number | null
  supported_generation_methods: string[]
  thinking: boolean
  chat_compatible: boolean
  is_default: boolean
}

export interface ModelCatalogResponse {
  defaultModel: string
  models: AvailableModel[]
}

export interface AvailableAgent {
  id: string
  name: string
  display_name: string
  description?: string | null
  provider: string
  default_model: string
}

export interface AgentCatalogResponse {
  defaultAgentId: string
  agents: AvailableAgent[]
}
