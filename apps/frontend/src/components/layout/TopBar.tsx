import {
  AlertCircle,
  CheckCircle2,
  Moon,
  RefreshCcw,
  Settings2,
  Sun,
  Sparkles,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Theme } from '@/hooks/useTheme'
import { cn } from '@/lib/utils'
import type {
  AgentCatalogResponse,
  AvailableAgent,
  AvailableModel,
  ModelCatalogResponse,
  RuntimeStatus,
} from '@/types'

interface TopBarProps {
  runtime: RuntimeStatus | null
  runtimeError: string | null
  conversationId?: string

  agentCatalog: AgentCatalogResponse | null
  agentCatalogError: string | null
  isLoadingAgentCatalog: boolean
  selectedAgent: string
  onSelectAgent: (id: string) => void
  onReloadAgents: () => void

  modelCatalog: ModelCatalogResponse | null
  modelCatalogError: string | null
  isLoadingModelCatalog: boolean
  chatCompatibleModels: AvailableModel[]
  nonChatCompatibleModels: AvailableModel[]
  selectedModel: string
  onSelectModel: (id: string) => void
  onReloadModels: () => void

  theme: Theme
  onToggleTheme: () => void
}

function buildModelLabel(model: AvailableModel): string {
  return model.display_name === model.id
    ? model.display_name
    : `${model.display_name} (${model.id})`
}

function buildAgentLabel(agent: AvailableAgent): string {
  return agent.display_name === agent.id
    ? agent.display_name
    : `${agent.display_name} (${agent.id})`
}

export function TopBar({
  runtime,
  runtimeError,
  conversationId,
  agentCatalog,
  agentCatalogError,
  isLoadingAgentCatalog,
  selectedAgent,
  onSelectAgent,
  onReloadAgents,
  modelCatalog,
  modelCatalogError,
  isLoadingModelCatalog,
  chatCompatibleModels,
  nonChatCompatibleModels,
  selectedModel,
  onSelectModel,
  onReloadModels,
  theme,
  onToggleTheme,
}: TopBarProps) {
  const runtimeReady = runtime?.ready === true
  const agents = agentCatalog?.agents ?? []
  const selectedAgentDisplay =
    agents.find((agent) => agent.id === selectedAgent)?.display_name ||
    runtime?.defaultAgentName ||
    'Visualizer'

  const statusTooltip = runtimeError
    ? runtimeError
    : runtimeReady
      ? `${selectedAgentDisplay} ready · receive → think → stream → finalize visual${
          runtime?.fallbackModel ? ` · fallback: ${runtime.fallbackModel}` : ''
        }`
      : `Set GOOGLE_API_KEY in ${runtime?.envSources.join(' or ') ?? 'the environment'} and reload.`

  return (
    <header className="sticky top-0 z-40 border-b border-border/80 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 py-3 md:px-8">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Sparkles className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-tight text-foreground">
              Visualizer Agent
            </div>
            <div className="truncate text-[11px] text-muted-foreground">
              {conversationId ?? 'New conversation'}
            </div>
          </div>
        </div>

        <div className="ml-2 flex min-w-0 items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge
                variant={runtimeReady ? 'success' : 'warning'}
                className="cursor-help"
              >
                {runtimeReady ? (
                  <CheckCircle2 className="size-3" />
                ) : (
                  <AlertCircle className="size-3" />
                )}
                {runtimeReady ? 'Agent ready' : 'Agent not ready'}
              </Badge>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-sm">
              <p className="text-xs leading-5">{statusTooltip}</p>
              {runtime ? (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  RPM {runtime.limits.requestsPerMinute} · TPM{' '}
                  {runtime.limits.tokensPerMinute.toLocaleString()} · RPD{' '}
                  {runtime.limits.requestsPerDay}
                </p>
              ) : null}
            </TooltipContent>
          </Tooltip>

          <Badge variant="secondary" className="hidden md:inline-flex">
            {selectedAgentDisplay}
          </Badge>
          <Badge variant="outline" className="hidden lg:inline-flex">
            {selectedModel || runtime?.model || 'gemini'}
          </Badge>
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2">
                <Settings2 className="size-4" />
                <span className="hidden sm:inline">Agent &amp; model</span>
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-[min(92vw,420px)] space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <label
                    htmlFor="agent-picker"
                    className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                  >
                    Agent
                  </label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 gap-1 text-xs"
                    onClick={onReloadAgents}
                    disabled={!runtimeReady || isLoadingAgentCatalog}
                  >
                    <RefreshCcw
                      className={cn('size-3', isLoadingAgentCatalog && 'animate-spin')}
                    />
                    {isLoadingAgentCatalog ? 'Refreshing' : 'Refresh'}
                  </Button>
                </div>
                <Select
                  value={selectedAgent || undefined}
                  onValueChange={onSelectAgent}
                  disabled={!runtimeReady || isLoadingAgentCatalog || agents.length === 0}
                >
                  <SelectTrigger id="agent-picker">
                    <SelectValue
                      placeholder={
                        !runtimeReady
                          ? 'Set a Gemini API key to load agents'
                          : isLoadingAgentCatalog
                            ? 'Loading agents…'
                            : 'No backend agents found'
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {buildAgentLabel(agent)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p
                  className={cn(
                    'text-[11px] leading-5',
                    agentCatalogError ? 'text-destructive' : 'text-muted-foreground',
                  )}
                >
                  {agentCatalogError
                    ? agentCatalogError
                    : !runtimeReady
                      ? 'Loads once a Gemini API key is available.'
                      : agentCatalog
                        ? `${agentCatalog.agents.length} backend agents. Switching resets the conversation.`
                        : 'Loading configured backend agents.'}
                </p>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <label
                    htmlFor="model-picker"
                    className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                  >
                    Model
                  </label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 gap-1 text-xs"
                    onClick={onReloadModels}
                    disabled={!runtimeReady || isLoadingModelCatalog}
                  >
                    <RefreshCcw
                      className={cn('size-3', isLoadingModelCatalog && 'animate-spin')}
                    />
                    {isLoadingModelCatalog ? 'Refreshing' : 'Refresh'}
                  </Button>
                </div>
                <Select
                  value={selectedModel || undefined}
                  onValueChange={onSelectModel}
                  disabled={
                    !runtimeReady || isLoadingModelCatalog || chatCompatibleModels.length === 0
                  }
                >
                  <SelectTrigger id="model-picker">
                    <SelectValue
                      placeholder={
                        !runtimeReady
                          ? 'Set a Gemini API key to load models'
                          : isLoadingModelCatalog
                            ? 'Loading models…'
                            : 'No selectable models'
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {chatCompatibleModels.length > 0 ? (
                      <SelectGroup>
                        <SelectLabel>Selectable for this chat</SelectLabel>
                        {chatCompatibleModels.map((model) => (
                          <SelectItem key={model.id} value={model.id}>
                            {buildModelLabel(model)}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ) : null}
                    {nonChatCompatibleModels.length > 0 ? (
                      <SelectGroup>
                        <SelectLabel>Visible, disabled here</SelectLabel>
                        {nonChatCompatibleModels.map((model) => (
                          <SelectItem key={model.id} value={model.id} disabled>
                            {buildModelLabel(model)}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ) : null}
                  </SelectContent>
                </Select>
                <p
                  className={cn(
                    'text-[11px] leading-5',
                    modelCatalogError ? 'text-destructive' : 'text-muted-foreground',
                  )}
                >
                  {modelCatalogError
                    ? modelCatalogError
                    : !runtimeReady
                      ? 'Loads once a Gemini API key is available.'
                      : modelCatalog
                        ? `${modelCatalog.models.length} visible · ${chatCompatibleModels.length} selectable · default ${modelCatalog.defaultModel}.`
                        : 'Loading Gemini catalog.'}
                </p>
              </div>
            </PopoverContent>
          </Popover>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onToggleTheme}
                aria-label={
                  theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
                }
              >
                {theme === 'dark' ? (
                  <Sun className="size-4" />
                ) : (
                  <Moon className="size-4" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              {theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
            </TooltipContent>
          </Tooltip>
        </div>
      </div>
    </header>
  )
}
