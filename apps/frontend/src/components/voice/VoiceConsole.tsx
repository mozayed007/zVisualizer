import {
  AlertTriangle,
  ChevronDown,
  Headphones,
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  RefreshCcw,
  Send,
  Volume2,
} from 'lucide-react'
import { forwardRef, useCallback, useEffect, useMemo, useRef, useState, useImperativeHandle } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import {
  finalizeLatestTranscript,
  updateTranscriptList,
  type TranscriptEntry,
} from '@/lib/transcript'
import type { RuntimeStatus, ServerEvent } from '@/types'

interface VoiceConsoleProps {
  runtime: RuntimeStatus | null
  selectedAgent: string
  selectedModel: string
  conversationId?: string
  onDelegatedTurnStart: (userMessage: string) => void
  onDelegatedServerEvent: (event: ServerEvent) => void
  onTranscriptTurnComplete?: (userText: string, assistantText: string) => void
}

type ConnectionState = 'disconnected' | 'connecting' | 'connected'

type DeviceKind = 'audioinput' | 'audiooutput'

type InputDeviceOption = { id: string; label: string }
type OutputDeviceOption = { id: string; label: string }

const WAVE_BAR_COUNT = 24
const DEFAULT_WAVE_SAMPLES: number[] = Array.from({ length: WAVE_BAR_COUNT }, () => 0.08)
const SPEECH_START_LEVEL = 0.02
const SPEECH_END_LEVEL = 0.012
const AUDIO_SILENCE_FLUSH_MS = 2000

function resolveApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL
  if (configured) return configured
  if (typeof window !== 'undefined') return window.location.origin
  return 'http://localhost:8000'
}

const apiBaseUrl = resolveApiBaseUrl()
const chatApiKey = import.meta.env.VITE_CHAT_API_KEY as string | undefined

function deriveWebSocketUrl(baseUrl: string): string {
  const url = new URL(baseUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/api/live'
  url.search = ''
  return url.toString()
}

function buildSessionUrl(baseUrl: string, params: Record<string, string | undefined>): string {
  const url = new URL(deriveWebSocketUrl(baseUrl))
  for (const [key, value] of Object.entries(params)) {
    if (value) url.searchParams.set(key, value)
  }
  if (chatApiKey) url.searchParams.set('api_key', chatApiKey)
  return url.toString()
}

function float32ToInt16Pcm(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length)
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i] ?? 0))
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return output
}

function downsampleTo16kHz(input: Float32Array, inputSampleRate: number): Int16Array {
  if (inputSampleRate === 16000) return float32ToInt16Pcm(input)
  const ratio = inputSampleRate / 16000
  const outputLength = Math.max(1, Math.round(input.length / ratio))
  const output = new Int16Array(outputLength)
  let outputIndex = 0
  let inputIndex = 0
  while (outputIndex < outputLength) {
    const nextInputIndex = Math.min(input.length, Math.round((outputIndex + 1) * ratio))
    let total = 0
    let count = 0
    while (inputIndex < nextInputIndex) {
      total += input[inputIndex] ?? 0
      count += 1
      inputIndex += 1
    }
    const sample = count > 0 ? total / count : 0
    const clamped = Math.max(-1, Math.min(1, sample))
    output[outputIndex] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff
    outputIndex += 1
  }
  return output
}

function int16ToBase64(samples: Int16Array): string {
  const bytes = new Uint8Array(samples.buffer)
  let binary = ''
  const chunkSize = 0x8000
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const chunk = bytes.subarray(offset, offset + chunkSize)
    binary += String.fromCharCode(...chunk)
  }
  return window.btoa(binary)
}

function base64ToInt16(base64Value: string): Int16Array {
  const binary = window.atob(base64Value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return new Int16Array(bytes.buffer)
}

function int16ToFloat32(samples: Int16Array): Float32Array {
  const output = new Float32Array(samples.length)
  for (let i = 0; i < samples.length; i += 1) output[i] = samples[i] / 0x8000
  return output
}

function pushWaveSample(current: number[], level: number): number[] {
  const normalizedLevel = Math.max(0.05, Math.min(1, level))
  return [...current.slice(-(WAVE_BAR_COUNT - 1)), normalizedLevel]
}

function calculateRmsLevel(samples: Int16Array): number {
  if (samples.length === 0) return 0
  let total = 0
  for (let i = 0; i < samples.length; i += 1) {
    const normalized = samples[i] / 0x8000
    total += normalized * normalized
  }
  return Math.min(1, Math.sqrt(total / samples.length) * 3.5)
}

function calculateFloat32RmsLevel(samples: Float32Array): number {
  if (samples.length === 0) return 0
  let total = 0
  for (let i = 0; i < samples.length; i += 1) {
    const normalized = samples[i] ?? 0
    total += normalized * normalized
  }
  return Math.min(1, Math.sqrt(total / samples.length) * 4)
}

function getMediaErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return 'Microphone access failed. Allow mic permission in the browser, then try again.'
  }
  const name = error.name.toLowerCase()
  const message = error.message.trim()
  if (message.includes('getUserMedia is not a function') || name.includes('security') || /secure context/i.test(message)) {
    return 'Microphone access requires a secure context (HTTPS or localhost).'
  }
  if (
    name.includes('notallowed') ||
    name.includes('permission') ||
    /permission denied|permission dismissed|not allowed/i.test(message)
  ) {
    return 'Microphone permission was denied. Allow microphone access for this page, then click Unmute.'
  }
  if (name.includes('notfound') || /requested device not found/i.test(message)) {
    return 'The selected microphone is not available. Pick another mic from the list and try again.'
  }
  if (name.includes('notreadable') || /device in use|could not start audio source/i.test(message)) {
    return 'The microphone is busy in another app. Close the other app or choose a different mic, then retry.'
  }
  return message || 'Microphone access failed. Allow mic permission in the browser, then try again.'
}

function getFallbackDeviceLabel(kind: DeviceKind, deviceId: string, index: number): string {
  if (deviceId === 'default') {
    return kind === 'audioinput' ? 'Default system microphone' : 'Default system speaker'
  }
  if (deviceId === 'communications') {
    return kind === 'audioinput' ? 'Communications microphone' : 'Communications speaker'
  }
  return kind === 'audioinput' ? `Microphone ${index + 1}` : `Speaker ${index + 1}`
}

function isGenericDeviceLabel(label: string, kind: DeviceKind): boolean {
  const normalized = label.trim().toLowerCase()
  if (!normalized) return true
  const patterns =
    kind === 'audioinput'
      ? [
          /^microphone \d+$/,
          /^default microphone$/,
          /^default system microphone$/,
          /^communications microphone$/,
        ]
      : [
          /^speaker \d+$/,
          /^default speaker$/,
          /^default system speaker$/,
          /^browser default speaker$/,
          /^communications speaker$/,
        ]
  return patterns.some((pattern) => pattern.test(normalized))
}

function VoiceWaveCard({
  label,
  status,
  isActive,
  samples,
  tone,
  icon: Icon,
}: {
  label: string
  status: string
  isActive: boolean
  samples: number[]
  tone: 'user' | 'assistant'
  icon: React.ComponentType<{ className?: string }>
}) {
  const toneClass =
    tone === 'user'
      ? 'from-primary/20 to-transparent'
      : 'from-emerald-500/20 to-transparent'
  const barClass =
    tone === 'user'
      ? 'bg-gradient-to-t from-primary/70 to-primary'
      : 'bg-gradient-to-t from-emerald-500/70 to-emerald-400'

  return (
    <div
      className={cn(
        'relative flex min-h-[140px] flex-col gap-3 overflow-hidden rounded-xl border bg-card/50 p-4',
        isActive ? 'border-primary/30 shadow-sm' : 'border-border',
      )}
    >
      <div
        className={cn(
          'pointer-events-none absolute inset-0 bg-gradient-to-br opacity-60',
          toneClass,
        )}
        aria-hidden="true"
      />
      <div className="relative flex items-center justify-between gap-2">
        <div className="inline-flex items-center gap-2 text-sm font-semibold text-foreground">
          <Icon className="size-4 opacity-80" />
          {label}
        </div>
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {status}
        </span>
      </div>
      <div
        className="relative grid flex-1 items-end gap-1"
        style={{ gridTemplateColumns: `repeat(${WAVE_BAR_COUNT}, minmax(0, 1fr))` }}
        aria-hidden="true"
      >
        {samples.map((sample, index) => (
          <span
            key={`${tone}-${index}`}
            className={cn('wave-bar', barClass)}
            style={{
              transform: `scaleY(${Math.max(0.12, sample)})`,
              opacity: isActive ? 0.78 + sample * 0.22 : 0.4,
            }}
          />
        ))}
      </div>
    </div>
  )
}

export interface VoiceConsoleRef {
  sendText: (text: string) => boolean
  isConnected: boolean
}

export const VoiceConsole = forwardRef<VoiceConsoleRef, VoiceConsoleProps>(function VoiceConsole(
  {
    runtime,
    selectedAgent,
    selectedModel,
    conversationId,
    onDelegatedTurnStart,
    onDelegatedServerEvent,
    onTranscriptTurnComplete,
  },
  ref,
) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [statusDetail, setStatusDetail] = useState('Start a voice session to talk with Gemini Live.')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isMicEnabled, setIsMicEnabled] = useState(false)
  const [draftText, setDraftText] = useState('')
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([])
  const [toolStatus, setToolStatus] = useState<string | null>(null)
  const [inputDevices, setInputDevices] = useState<InputDeviceOption[]>([])
  const [outputDevices, setOutputDevices] = useState<OutputDeviceOption[]>([])
  const [selectedInputId, setSelectedInputId] = useState('default')
  const [selectedOutputId, setSelectedOutputId] = useState('default')
  const [userWaveSamples, setUserWaveSamples] = useState<number[]>(DEFAULT_WAVE_SAMPLES)
  const [assistantWaveSamples, setAssistantWaveSamples] = useState<number[]>(DEFAULT_WAVE_SAMPLES)
  const [userAudioLevel, setUserAudioLevel] = useState(0)
  const [assistantIsSpeaking, setAssistantIsSpeaking] = useState(false)
  const [speakerSelectionSupported, setSpeakerSelectionSupported] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [hasManuallyMuted, setHasManuallyMuted] = useState(false)
  const [localMicMonitoring, setLocalMicMonitoring] = useState(false)
  const [monitoringGain, setMonitoringGain] = useState(0.3)

  const websocketRef = useRef<WebSocket | null>(null)
  const captureContextRef = useRef<AudioContext | null>(null)
  const playbackContextRef = useRef<AudioContext | null>(null)
  const playbackDestinationRef = useRef<MediaStreamAudioDestinationNode | null>(null)
  const playbackAnalyserRef = useRef<AnalyserNode | null>(null)
  const playbackAudioRef = useRef<HTMLAudioElement | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const captureProcessorRef = useRef<ScriptProcessorNode | null>(null)
  const captureSourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const silentGainRef = useRef<GainNode | null>(null)
  const monitoringGainRef = useRef<GainNode | null>(null)
  const playbackCursorRef = useRef(0)
  const activePlaybackSourcesRef = useRef<AudioBufferSourceNode[]>([])
  const micEnabledRef = useRef(false)
  const desiredMicEnabledRef = useRef(true)
  const userWaveAnimationFrameRef = useRef<number | null>(null)
  const assistantWaveAnimationFrameRef = useRef<number | null>(null)
  const silenceFlushTimeoutRef = useRef<number | null>(null)
  const audioTurnOpenRef = useRef(false)
  const shouldAutoReconnectRef = useRef(false)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const openSessionRef = useRef<() => Promise<void>>(async () => {})

  const canUseVoice = useMemo(
    () => runtime?.ready === true && runtime.live.ready,
    [runtime],
  )

  // Auto-expand when connected, collapse when idle.
  useEffect(() => {
    if (connectionState === 'connected' || connectionState === 'connecting') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setExpanded(true)
    }
  }, [connectionState])

  const refreshInputDevices = useCallback(
    async (options?: { requestPermissionIfNeeded?: boolean }) => {
      if (!navigator.mediaDevices?.enumerateDevices) return
      try {
        let devices = await navigator.mediaDevices.enumerateDevices()
        const audioInputDevices = devices.filter((device) => device.kind === 'audioinput')
        const shouldRequestPermission =
          options?.requestPermissionIfNeeded === true &&
          !mediaStreamRef.current &&
          audioInputDevices.length > 0 &&
          audioInputDevices.every((device, index) =>
            isGenericDeviceLabel(
              device.label || getFallbackDeviceLabel('audioinput', device.deviceId, index),
              'audioinput',
            ),
          )

        if (shouldRequestPermission && navigator.mediaDevices.getUserMedia) {
          try {
            const probeStream = await navigator.mediaDevices.getUserMedia({ audio: true })
            probeStream.getTracks().forEach((track) => track.stop())
            devices = await navigator.mediaDevices.enumerateDevices()
          } catch {
            // Keep generic labels if the browser blocks the permission probe.
          }
        }

        const nextInputs = devices
          .filter((device) => device.kind === 'audioinput')
          .map((device, index) => ({
            id: device.deviceId || `input-${index}`,
            label: device.label || getFallbackDeviceLabel('audioinput', device.deviceId, index),
          }))
        const nextOutputs = devices
          .filter((device) => device.kind === 'audiooutput')
          .map((device, index) => ({
            id: device.deviceId || `output-${index}`,
            label: device.label || getFallbackDeviceLabel('audiooutput', device.deviceId, index),
          }))

        setInputDevices(nextInputs)
        setOutputDevices(nextOutputs)
        setSelectedInputId((current) => {
          if (nextInputs.length === 0) return 'default'
          if (current !== 'default' && nextInputs.some((device) => device.id === current)) {
            return current
          }
          return nextInputs[0]?.id ?? 'default'
        })
        setSelectedOutputId((current) => {
          if (nextOutputs.length === 0) return 'default'
          if (current !== 'default' && nextOutputs.some((device) => device.id === current)) {
            return current
          }
          return nextOutputs[0]?.id ?? 'default'
        })
      } catch {
        // Ignore device enumeration failures.
      }
    },
    [],
  )

  const sendJson = useCallback((payload: Record<string, unknown>) => {
    const socket = websocketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify(payload))
    return true
  }, [])

  const clearPendingSilenceFlush = useCallback(() => {
    if (silenceFlushTimeoutRef.current !== null) {
      window.clearTimeout(silenceFlushTimeoutRef.current)
      silenceFlushTimeoutRef.current = null
    }
  }, [])

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current !== null) {
      window.clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }, [])

  const flushAudioTurn = useCallback(
    (detail?: string) => {
      clearPendingSilenceFlush()
      if (!audioTurnOpenRef.current) return false
      audioTurnOpenRef.current = false
      const sent = sendJson({ type: 'input.audio_end' })
      if (sent && detail) setStatusDetail(detail)
      return sent
    },
    [clearPendingSilenceFlush, sendJson],
  )

  const openAudioTurn = useCallback(
    (detail?: string) => {
      clearPendingSilenceFlush()
      if (audioTurnOpenRef.current) return true
      const sent = sendJson({ type: 'input.audio_start' })
      if (!sent) return false
      audioTurnOpenRef.current = true
      if (detail) setStatusDetail(detail)
      return true
    },
    [clearPendingSilenceFlush, sendJson],
  )

  const stopPlayback = useCallback(() => {
    for (const source of activePlaybackSourcesRef.current) {
      try {
        source.stop()
      } catch {
        // Ignore stop races when sources already ended.
      }
    }
    activePlaybackSourcesRef.current = []
    if (assistantWaveAnimationFrameRef.current !== null) {
      window.cancelAnimationFrame(assistantWaveAnimationFrameRef.current)
      assistantWaveAnimationFrameRef.current = null
    }
    setAssistantIsSpeaking(false)
    setAssistantWaveSamples(DEFAULT_WAVE_SAMPLES)
    const playbackContext = playbackContextRef.current
    playbackCursorRef.current = playbackContext ? playbackContext.currentTime : 0
  }, [])

  const applySpeakerSelection = useCallback(async (deviceId: string) => {
    const audioElement = playbackAudioRef.current as
      | (HTMLAudioElement & { setSinkId?: (sinkId: string) => Promise<void> })
      | null

    if (!audioElement || typeof audioElement.setSinkId !== 'function') {
      setSpeakerSelectionSupported(false)
      return
    }

    setSpeakerSelectionSupported(true)
    await audioElement.setSinkId(deviceId === 'default' ? '' : deviceId)
  }, [])

  const ensurePlaybackContext = useCallback(async () => {
    let context = playbackContextRef.current
    if (!context) {
      context = new AudioContext()
      playbackContextRef.current = context
      playbackCursorRef.current = context.currentTime
      const destination = context.createMediaStreamDestination()
      playbackDestinationRef.current = destination
      const analyser = context.createAnalyser()
      analyser.fftSize = 1024
      analyser.connect(destination)
      playbackAnalyserRef.current = analyser

      const audioElement = new Audio()
      audioElement.autoplay = true
      audioElement.srcObject = destination.stream
      audioElement.muted = false
      playbackAudioRef.current = audioElement

      // Detect sinkId support as soon as the element exists.
      setSpeakerSelectionSupported(
        typeof (audioElement as HTMLAudioElement & { setSinkId?: unknown }).setSinkId ===
          'function',
      )
    }
    if (context.state === 'suspended') {
      await context.resume()
    }
    const audioElement = playbackAudioRef.current
    if (audioElement) {
      try {
        await audioElement.play()
      } catch {
        // Browser autoplay policies can defer playback until user interaction.
      }
    }
    return context
  }, [])

  const queuePlaybackChunk = useCallback(
    async (base64Audio: string) => {
      const context = await ensurePlaybackContext()
      const pcm = base64ToInt16(base64Audio)
      const level = calculateRmsLevel(pcm)
      setAssistantIsSpeaking(true)
      const floatSamples = int16ToFloat32(pcm)
      const buffer = context.createBuffer(1, floatSamples.length, 24000)
      buffer.copyToChannel(new Float32Array(floatSamples), 0)
      const source = context.createBufferSource()
      source.buffer = buffer
      const playbackAnalyser = playbackAnalyserRef.current
      if (playbackAnalyser) {
        source.connect(playbackAnalyser)
      } else {
        source.connect(playbackDestinationRef.current ?? context.destination)
      }
      const startAt = Math.max(playbackCursorRef.current, context.currentTime + 0.02)
      source.start(startAt)
      playbackCursorRef.current = startAt + buffer.duration
      activePlaybackSourcesRef.current.push(source)

      if (assistantWaveAnimationFrameRef.current === null && playbackAnalyser) {
        const waveformBuffer = new Uint8Array(playbackAnalyser.frequencyBinCount)
        const animateAssistantWave = () => {
          const analyser = playbackAnalyserRef.current
          if (!analyser) {
            assistantWaveAnimationFrameRef.current = null
            return
          }
          analyser.getByteTimeDomainData(waveformBuffer)
          let total = 0
          for (let i = 0; i < waveformBuffer.length; i += 1) {
            const centered = (waveformBuffer[i] - 128) / 128
            total += centered * centered
          }
          const liveLevel = Math.min(1, Math.sqrt(total / waveformBuffer.length) * 4)
          const smoothedLevel = Math.max(liveLevel, level * 0.35)
          setAssistantWaveSamples((current) => pushWaveSample(current, smoothedLevel))
          if (activePlaybackSourcesRef.current.length === 0) {
            assistantWaveAnimationFrameRef.current = null
            return
          }
          assistantWaveAnimationFrameRef.current = window.requestAnimationFrame(animateAssistantWave)
        }
        assistantWaveAnimationFrameRef.current = window.requestAnimationFrame(animateAssistantWave)
      }

      source.onended = () => {
        activePlaybackSourcesRef.current = activePlaybackSourcesRef.current.filter(
          (candidate) => candidate !== source,
        )
        if (activePlaybackSourcesRef.current.length === 0) {
          setAssistantIsSpeaking(false)
          setAssistantWaveSamples((current) => pushWaveSample(current, 0.06))
        }
      }
    },
    [ensurePlaybackContext],
  )

  const stopMicrophone = useCallback(() => {
    clearPendingSilenceFlush()
    if (userWaveAnimationFrameRef.current !== null) {
      window.cancelAnimationFrame(userWaveAnimationFrameRef.current)
      userWaveAnimationFrameRef.current = null
    }
    micEnabledRef.current = false
    audioTurnOpenRef.current = false
    captureProcessorRef.current?.disconnect()
    captureSourceRef.current?.disconnect()
    analyserRef.current?.disconnect()
    silentGainRef.current?.disconnect()
    monitoringGainRef.current?.disconnect()
    captureProcessorRef.current = null
    captureSourceRef.current = null
    analyserRef.current = null
    silentGainRef.current = null
    monitoringGainRef.current = null
    setUserAudioLevel(0)
    setUserWaveSamples(DEFAULT_WAVE_SAMPLES)

    const mediaStream = mediaStreamRef.current
    if (mediaStream) {
      for (const track of mediaStream.getTracks()) track.stop()
    }
    mediaStreamRef.current = null

    const captureContext = captureContextRef.current
    captureContextRef.current = null
    if (captureContext) void captureContext.close()
  }, [clearPendingSilenceFlush])

  const setMicrophoneTrackEnabled = useCallback((enabled: boolean) => {
    const mediaStream = mediaStreamRef.current
    if (!mediaStream) return false
    for (const track of mediaStream.getAudioTracks()) track.enabled = enabled
    setUserAudioLevel(0)
    setUserWaveSamples(DEFAULT_WAVE_SAMPLES)
    return true
  }, [])

  const toggleMicMonitoring = useCallback((enabled: boolean) => {
    setLocalMicMonitoring(enabled)
    if (monitoringGainRef.current) {
      monitoringGainRef.current.gain.value = enabled ? monitoringGain : 0
    }
  }, [monitoringGain])

  useEffect(() => {
    if (monitoringGainRef.current) {
      monitoringGainRef.current.gain.value = localMicMonitoring ? monitoringGain : 0
    }
  }, [localMicMonitoring, monitoringGain])

  const startMicrophone = useCallback(async () => {
    const socket = websocketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      throw new Error('Open the voice session before enabling the microphone.')
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('getUserMedia is not a function (Microphone requires HTTPS/localhost)')
    }

    const mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: selectedInputId !== 'default' ? { exact: selectedInputId } : undefined,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    const captureContext = new AudioContext()
    const source = captureContext.createMediaStreamSource(mediaStream)
    const analyser = captureContext.createAnalyser()
    analyser.fftSize = 1024
    const processor = captureContext.createScriptProcessor(4096, 1, 1)
    const silentGain = captureContext.createGain()
    silentGain.gain.value = 0
    const monitoringGainNode = captureContext.createGain()
    monitoringGainNode.gain.value = localMicMonitoring ? monitoringGain : 0

    processor.onaudioprocess = (event) => {
      if (
        !websocketRef.current ||
        websocketRef.current.readyState !== WebSocket.OPEN ||
        !micEnabledRef.current
      ) {
        return
      }
      const inputData = event.inputBuffer.getChannelData(0)
      const level = calculateFloat32RmsLevel(inputData)

      if (level >= SPEECH_START_LEVEL) {
        clearPendingSilenceFlush()
        if (!audioTurnOpenRef.current) {
          const opened = openAudioTurn('Listening to your voice turn…')
          if (!opened) return
        }
      } else if (
        audioTurnOpenRef.current &&
        level <= SPEECH_END_LEVEL &&
        silenceFlushTimeoutRef.current === null
      ) {
        silenceFlushTimeoutRef.current = window.setTimeout(() => {
          silenceFlushTimeoutRef.current = null
          if (!micEnabledRef.current || !audioTurnOpenRef.current) return
          const socket = websocketRef.current
          if (!socket || socket.readyState !== WebSocket.OPEN) {
            // Socket died during the silence window; reset turn state so the UI doesn't stall.
            audioTurnOpenRef.current = false
            return
          }
          flushAudioTurn('Voice turn sent. Waiting for Gemini Live.')
        }, AUDIO_SILENCE_FLUSH_MS)
      }

      if (!audioTurnOpenRef.current) return

      const downsampled = downsampleTo16kHz(inputData, captureContext.sampleRate)
      if (downsampled.length === 0) return
      websocketRef.current.send(
        JSON.stringify({
          type: 'input.audio',
          audio: int16ToBase64(downsampled),
        }),
      )
    }

    const waveformBuffer = new Uint8Array(analyser.frequencyBinCount)
    const animateWave = () => {
      analyser.getByteTimeDomainData(waveformBuffer)
      let total = 0
      for (let i = 0; i < waveformBuffer.length; i += 1) {
        const centered = (waveformBuffer[i] - 128) / 128
        total += centered * centered
      }
      const level = Math.min(1, Math.sqrt(total / waveformBuffer.length) * 4)
      setUserAudioLevel(level)
      setUserWaveSamples((current) => pushWaveSample(current, level))
      userWaveAnimationFrameRef.current = window.requestAnimationFrame(animateWave)
    }

    source.connect(analyser)
    source.connect(processor)
    processor.connect(silentGain)
    silentGain.connect(captureContext.destination)
    source.connect(monitoringGainNode)
    monitoringGainNode.connect(captureContext.destination)
    micEnabledRef.current = true
    audioTurnOpenRef.current = false
    clearPendingSilenceFlush()
    animateWave()

    mediaStreamRef.current = mediaStream
    captureContextRef.current = captureContext
    captureSourceRef.current = source
    analyserRef.current = analyser
    captureProcessorRef.current = processor
    silentGainRef.current = silentGain
    monitoringGainRef.current = monitoringGainNode
    await refreshInputDevices()
  }, [clearPendingSilenceFlush, flushAudioTurn, openAudioTurn, refreshInputDevices, selectedInputId, localMicMonitoring, monitoringGain])

  const closeSession = useCallback(
    (options?: { allowReconnect?: boolean }) => {
      shouldAutoReconnectRef.current = options?.allowReconnect === true
      if (!shouldAutoReconnectRef.current) {
        clearReconnectTimeout()
        reconnectAttemptsRef.current = 0
      }
      flushAudioTurn()
      stopMicrophone()
      stopPlayback()

      const socket = websocketRef.current
      websocketRef.current = null
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'close' }))
        socket.close()
      }
      setConnectionState('disconnected')
      setIsMicEnabled(false)
      setStatusDetail(
        shouldAutoReconnectRef.current ? 'Voice session reconnecting…' : 'Voice session closed.',
      )
    },
    [clearReconnectTimeout, flushAudioTurn, stopMicrophone, stopPlayback],
  )

  // eslint-disable-next-line react-hooks/preserve-manual-memoization
  const openSession = useCallback(async () => {
    if (!canUseVoice) {
      setErrorMessage('Gemini Live is not ready until the backend has a Gemini API key.')
      return
    }

    setConnectionState('connecting')
    setErrorMessage(null)
    setToolStatus(null)
    setTranscripts([])
    setStatusDetail('Connecting to Gemini Live…')

    const socket = new WebSocket(
      buildSessionUrl(apiBaseUrl, {
        agent_id: selectedAgent || runtime?.defaultAgentId,
        model: selectedModel || runtime?.model,
        conversation_id: conversationId,
      }),
    )
    websocketRef.current = socket

    socket.onopen = async () => {
      clearReconnectTimeout()
      reconnectAttemptsRef.current = 0
      shouldAutoReconnectRef.current = true
      setConnectionState('connected')
      setStatusDetail('Voice session connected. Requesting microphone access…')
      try {
        await ensurePlaybackContext()
        await applySpeakerSelection(selectedOutputId)
        if (desiredMicEnabledRef.current) {
          await startMicrophone()
          setIsMicEnabled(true)
          micEnabledRef.current = true
        } else {
          setIsMicEnabled(false)
          micEnabledRef.current = false
          setStatusDetail('Voice session connected. Microphone is muted.')
        }
        sendJson({
          type: 'session.update',
          agentId: selectedAgent || runtime?.defaultAgentId,
          model: selectedModel || runtime?.model,
          conversationId,
        })
      } catch (error) {
        setIsMicEnabled(false)
        micEnabledRef.current = false
        setErrorMessage(getMediaErrorMessage(error))
      }
    }

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as Record<string, unknown>
        const messageType = typeof message.type === 'string' ? message.type : ''

        if (messageType === 'state' && typeof message.detail === 'string') {
          setStatusDetail(message.detail)
          return
        }

        if (messageType === 'session.ready') {
          setStatusDetail('Voice session ready. Start talking.')
          return
        }

        if (messageType === 'transcript') {
          const role: TranscriptEntry['role'] =
            message.role === 'assistant' ? 'assistant' : 'user'
          const text = typeof message.text === 'string' ? message.text : ''
          const final = message.final === true
          if (!text) return
          setTranscripts((current) =>
            updateTranscriptList(current, { role, text, final }),
          )
          return
        }

        if (messageType === 'turn.complete') {
          setTranscripts((current) => {
            const userEntry = current.findLast((e) => e.role === 'user' && !e.final)
            const assistantEntry = current.findLast((e) => e.role === 'assistant' && !e.final)
            
            if (userEntry?.text || assistantEntry?.text) {
              onTranscriptTurnComplete?.(userEntry?.text || '', assistantEntry?.text || '')
            }

            return finalizeLatestTranscript(finalizeLatestTranscript(current, 'assistant'), 'user')
          })
          return
        }

        if (messageType === 'text.output' && typeof message.text === 'string') {
          const text = message.text
          if (!text) return
          setTranscripts((current) =>
            updateTranscriptList(current, { role: 'assistant', text, final: false }),
          )
          return
        }

        if (messageType === 'session.updated') {
          const agentId = typeof message.agentId === 'string' ? message.agentId : null
          const model = typeof message.model === 'string' ? message.model : null
          if (agentId || model) {
            const detail = [agentId ? `agent ${agentId}` : null, model ? `model ${model}` : null]
              .filter(Boolean)
              .join(' · ')
            setStatusDetail(`Live session updated (${detail}).`)
          }
          return
        }

        if (messageType === 'audio.output' && typeof message.audio === 'string') {
          void queuePlaybackChunk(message.audio)
          return
        }

        if (messageType === 'audio.interrupted') {
          stopPlayback()
          return
        }

        if (messageType === 'agent.turn_started' && typeof message.userMessage === 'string') {
          setToolStatus('Visualizer agent is working on your request…')
          onDelegatedTurnStart(message.userMessage)
          return
        }

        if (
          messageType === 'agent.event' &&
          typeof message.event === 'object' &&
          message.event !== null
        ) {
          onDelegatedServerEvent(message.event as ServerEvent)
          return
        }

        if (messageType === 'agent.result') {
          if (message.error && typeof message.error === 'string') {
            setToolStatus(`Delegation failed: ${message.error}`)
          } else if (message.visual_ready === true) {
            setToolStatus(
              message.background_mode === true
                ? 'Visual finished in chat. Gemini can keep talking and now has the result available to explain.'
                : 'Visual finished in chat. Gemini can now explain it to you.',
            )
          } else {
            setToolStatus('Delegated chat answer finished without a visual.')
          }
          return
        }

        if (messageType === 'agent.notice' && typeof message.detail === 'string') {
          setToolStatus(message.detail)
          return
        }

        if (messageType === 'error' && typeof message.detail === 'string') {
          setErrorMessage(message.detail)
        }
      } catch {
        setErrorMessage('Received an unreadable realtime message from the backend.')
      }
    }

    socket.onerror = () => {
      setErrorMessage('The realtime voice socket hit a transport error.')
    }

    socket.onclose = () => {
      websocketRef.current = null
      clearPendingSilenceFlush()
      audioTurnOpenRef.current = false
      stopMicrophone()
      stopPlayback()
      setConnectionState('disconnected')
      setIsMicEnabled(false)
      if (shouldAutoReconnectRef.current && reconnectAttemptsRef.current < 8) {
        reconnectAttemptsRef.current += 1
        setStatusDetail('Voice session dropped. Reconnecting…')
        clearReconnectTimeout()
        reconnectTimeoutRef.current = window.setTimeout(() => {
          reconnectTimeoutRef.current = null
          if (!shouldAutoReconnectRef.current || !canUseVoice) return
          void openSessionRef.current()
        }, 900)
        return
      }
      shouldAutoReconnectRef.current = false
      setStatusDetail('Voice session disconnected.')
    }
  }, [
    applySpeakerSelection,
    canUseVoice,
    clearPendingSilenceFlush,
    clearReconnectTimeout,
    conversationId,
    ensurePlaybackContext,
    onDelegatedServerEvent,
    onDelegatedTurnStart,
    queuePlaybackChunk,
    runtime?.defaultAgentId,
    runtime?.model,
    selectedAgent,
    selectedModel,
    selectedOutputId,
    sendJson,
    startMicrophone,
    stopMicrophone,
    stopPlayback,
  ])

  useEffect(() => {
    openSessionRef.current = openSession
  }, [openSession])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshInputDevices()
    const mediaDevices = navigator.mediaDevices
    const handleDeviceChange = () => {
      void refreshInputDevices()
    }
    mediaDevices?.addEventListener?.('devicechange', handleDeviceChange)
    return () => {
      mediaDevices?.removeEventListener?.('devicechange', handleDeviceChange)
    }
  }, [refreshInputDevices])

  useEffect(() => {
    if (connectionState !== 'connected') return
    sendJson({
      type: 'session.update',
      agentId: selectedAgent || runtime?.defaultAgentId,
      model: selectedModel || runtime?.model,
      conversationId,
    })
  }, [
    connectionState,
    conversationId,
    runtime?.defaultAgentId,
    runtime?.model,
    selectedAgent,
    selectedModel,
    sendJson,
  ])

  useEffect(() => {
    return () => {
      shouldAutoReconnectRef.current = false
      clearReconnectTimeout()
      closeSession()
    }
  }, [clearReconnectTimeout, closeSession])

  const handleToggleMic = async () => {
    if (connectionState !== 'connected') return
    if (isMicEnabled) {
      desiredMicEnabledRef.current = false
      setHasManuallyMuted(true)
      setErrorMessage(null)
      setIsMicEnabled(false)
      micEnabledRef.current = false
      flushAudioTurn('Microphone muted. You can still send text into the live session.')
      setMicrophoneTrackEnabled(false)
      setStatusDetail('Microphone muted. The live session stays open while you talk to viewers.')
      return
    }
    try {
      desiredMicEnabledRef.current = true
      setHasManuallyMuted(false)
      const resumedExistingStream = setMicrophoneTrackEnabled(true)
      if (!resumedExistingStream) {
        stopMicrophone()
        await startMicrophone()
      }
      micEnabledRef.current = true
      setIsMicEnabled(true)
      setErrorMessage(null)
      setStatusDetail('Microphone live. Speak naturally.')
    } catch (error) {
      desiredMicEnabledRef.current = false
      setIsMicEnabled(false)
      micEnabledRef.current = false
      setErrorMessage(getMediaErrorMessage(error))
    }
  }

  const handleSendText = () => {
    const text = draftText.trim()
    if (!text) return
    const sent = sendJson({ type: 'input.text', text })
    if (sent) {
      setDraftText('')
      setStatusDetail('Sent your text into the live session.')
    }
  }

  const handleMicSelection = async (nextId: string) => {
    setSelectedInputId(nextId)
    if (!isMicEnabled || connectionState !== 'connected') return
    try {
      flushAudioTurn()
      desiredMicEnabledRef.current = true
      micEnabledRef.current = false
      stopMicrophone()
      await startMicrophone()
      micEnabledRef.current = true
      setIsMicEnabled(true)
      setErrorMessage(null)
      setStatusDetail('Switched microphone input for the live session.')
    } catch (error) {
      setIsMicEnabled(false)
      micEnabledRef.current = false
      setErrorMessage(getMediaErrorMessage(error))
    }
  }

  const handleSpeakerSelection = async (nextId: string) => {
    setSelectedOutputId(nextId)
    try {
      await ensurePlaybackContext()
      await applySpeakerSelection(nextId)
      setStatusDetail('Speaker output updated for Gemini Live playback.')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not switch speaker output.')
    }
  }

  const lastTranscript = transcripts[transcripts.length - 1]
  const inputLabelsHidden =
    inputDevices.length > 0 &&
    inputDevices.every((device) => isGenericDeviceLabel(device.label, 'audioinput'))
  const outputLabelsHidden =
    outputDevices.length > 0 &&
    outputDevices.every((device) => isGenericDeviceLabel(device.label, 'audiooutput'))
  const sessionPreservedWhileMuted =
    connectionState === 'connected' && !isMicEnabled && hasManuallyMuted

  const connectionBadgeVariant =
    connectionState === 'connected'
      ? 'success'
      : connectionState === 'connecting'
        ? 'warning'
        : 'secondary'

  const startButton = (
    <Button
      variant="default"
      size="sm"
      className="gap-2"
      disabled={!canUseVoice || connectionState === 'connecting'}
      onClick={() => void openSession()}
    >
      <Phone className="size-4" />
      {connectionState === 'connecting' ? 'Connecting…' : 'Start voice'}
    </Button>
  )

  useImperativeHandle(
    ref,
    () => ({
      sendText: (text: string) => {
        if (connectionState !== 'connected') return false
        const sent = sendJson({ type: 'input.text', text })
        if (sent) {
          setStatusDetail('Sent your text into the live session.')
        }
        return sent
      },
      isConnected: connectionState === 'connected',
    }),
    [connectionState, sendJson],
  )

  return (
    <Collapsible
      open={expanded}
      onOpenChange={setExpanded}
      className="mx-auto w-full max-w-5xl overflow-hidden rounded-2xl border border-border bg-card/60 backdrop-blur"
    >
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 md:px-5">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div
            className={cn(
              'flex size-9 items-center justify-center rounded-full border',
              connectionState === 'connected'
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-500'
                : 'border-border bg-muted text-muted-foreground',
            )}
          >
            <Headphones className="size-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-sm font-semibold text-foreground">
                Live voice agent
              </h2>
              <Badge variant={connectionBadgeVariant} className="capitalize">
                {connectionState}
              </Badge>
            </div>
            <p className="truncate text-xs text-muted-foreground">{statusDetail}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {connectionState === 'connected' ? (
            <>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={isMicEnabled ? 'secondary' : 'outline'}
                    size="sm"
                    className="gap-2"
                    onClick={() => void handleToggleMic()}
                  >
                    {isMicEnabled ? (
                      <Mic className="size-4 text-emerald-500" />
                    ) : (
                      <MicOff className="size-4" />
                    )}
                    {isMicEnabled ? 'Mute' : 'Unmute'}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  {isMicEnabled ? 'Mute the microphone' : 'Unmute the microphone'}
                </TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={localMicMonitoring ? 'secondary' : 'outline'}
                    size="sm"
                    className="gap-2"
                    onClick={() => void toggleMicMonitoring(!localMicMonitoring)}
                  >
                    <Headphones className="size-4" />
                    Monitor
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  {localMicMonitoring
                    ? 'Disable local mic monitoring'
                    : 'Enable local mic monitoring (for screen recording)'}
                </TooltipContent>
              </Tooltip>
              {localMicMonitoring && (
                <div className="flex items-center gap-2 px-2">
                  <span className="text-xs text-muted-foreground">Level:</span>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={monitoringGain}
                    onChange={(e) => {
                      const value = parseFloat(e.target.value)
                      setMonitoringGain(value)
                      if (monitoringGainRef.current) {
                        monitoringGainRef.current.gain.value = value
                      }
                    }}
                    className="w-16 h-1 accent-primary"
                  />
                </div>
              )}
              <Button
                variant="destructive"
                size="sm"
                className="gap-2"
                onClick={() => {
                  shouldAutoReconnectRef.current = false
                  closeSession()
                }}
              >
                <PhoneOff className="size-4" />
                End
              </Button>
            </>
          ) : canUseVoice ? (
            startButton
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>{startButton}</span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                Gemini Live is not ready. Ensure the backend has a Gemini API key and that the
                Live endpoint is reachable.
              </TooltipContent>
            </Tooltip>
          )}
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={expanded ? 'Collapse voice panel' : 'Expand voice panel'}
            >
              <ChevronDown
                className={cn(
                  'size-4 transition-transform duration-200',
                  expanded && 'rotate-180',
                )}
              />
            </Button>
          </CollapsibleTrigger>
        </div>
      </div>

      <CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
        <div className="space-y-4 border-t border-border px-4 py-4 md:px-5">
          {sessionPreservedWhileMuted ? (
            <div className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-foreground">
              <strong className="font-semibold">Session preserved while muted.</strong>{' '}
              Gemini Live stays connected while your mic is muted, so you can keep demoing and
              unmute when ready.
            </div>
          ) : null}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <VoiceWaveCard
              label="You"
              status={isMicEnabled ? 'Mic live' : 'Mic idle'}
              isActive={isMicEnabled && userAudioLevel > 0.03}
              samples={userWaveSamples}
              tone="user"
              icon={Mic}
            />
            <VoiceWaveCard
              label={runtime?.live.voice ?? 'Gemini Live'}
              status={assistantIsSpeaking ? 'Speaking' : 'Waiting'}
              isActive={assistantIsSpeaking}
              samples={assistantWaveSamples}
              tone="assistant"
              icon={Volume2}
            />
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <label
                  htmlFor="voice-mic-picker"
                  className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  Mic input
                </label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-xs"
                  onClick={() => void refreshInputDevices({ requestPermissionIfNeeded: true })}
                >
                  <RefreshCcw className="size-3" />
                  Refresh
                </Button>
              </div>
              <Select
                value={selectedInputId}
                onValueChange={(value) => void handleMicSelection(value)}
              >
                <SelectTrigger id="voice-mic-picker">
                  <SelectValue placeholder="Default microphone" />
                </SelectTrigger>
                <SelectContent>
                  {inputDevices.length === 0 ? (
                    <SelectItem value="default">Default microphone</SelectItem>
                  ) : (
                    inputDevices.map((device) => (
                      <SelectItem key={device.id} value={device.id}>
                        {device.label}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
              {inputLabelsHidden && window.isSecureContext ? (
                <p className="text-[11px] leading-5 text-muted-foreground">
                  Browser is hiding real mic names. Allow microphone access and refresh to unlock
                  labels.
                </p>
              ) : !window.isSecureContext ? (
                <p className="text-[11px] leading-5 text-destructive">
                  Microphone access requires a secure context (HTTPS or localhost).
                </p>
              ) : null}
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <label
                  htmlFor="voice-speaker-picker"
                  className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  Speaker output
                </label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-xs"
                  onClick={() => void refreshInputDevices()}
                >
                  <RefreshCcw className="size-3" />
                  Refresh
                </Button>
              </div>
              <Select
                value={selectedOutputId}
                onValueChange={(value) => void handleSpeakerSelection(value)}
                disabled={!speakerSelectionSupported && outputDevices.length === 0}
              >
                <SelectTrigger id="voice-speaker-picker">
                  <SelectValue
                    placeholder={
                      speakerSelectionSupported ? 'Default speaker' : 'Browser default speaker'
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {outputDevices.length === 0 ? (
                    <SelectItem value="default">
                      {speakerSelectionSupported ? 'Default speaker' : 'Browser default speaker'}
                    </SelectItem>
                  ) : (
                    outputDevices.map((device) => (
                      <SelectItem key={device.id} value={device.id}>
                        {device.label}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
              {!speakerSelectionSupported ? (
                <p className="text-[11px] leading-5 text-muted-foreground">
                  Speaker routing depends on browser support for output-device selection.
                </p>
              ) : outputLabelsHidden && window.isSecureContext ? (
                <p className="text-[11px] leading-5 text-muted-foreground">
                  Browser is hiding real speaker names. Chromium reveals better labels after
                  media permission is granted.
                </p>
              ) : !window.isSecureContext ? (
                <p className="text-[11px] leading-5 text-destructive">
                  Device selection requires a secure context (HTTPS or localhost).
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex flex-col gap-2 md:flex-row md:items-start">
            <Textarea
              value={draftText}
              onChange={(event) => setDraftText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault()
                  if (connectionState === 'connected' && draftText.trim()) {
                    handleSendText()
                  }
                }
              }}
              rows={2}
              placeholder="Optional fallback: type into the live voice session if you don't want to speak."
              disabled={connectionState !== 'connected'}
              className="flex-1"
            />
            <Button
              type="button"
              variant="outline"
              size="default"
              onClick={handleSendText}
              disabled={connectionState !== 'connected' || !draftText.trim()}
              className="gap-2"
            >
              <Send className="size-4" />
              Send
            </Button>
          </div>

          {toolStatus ? (
            <div className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-foreground">
              {toolStatus}
            </div>
          ) : null}
          {errorMessage ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-foreground">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
              <span>{errorMessage}</span>
            </div>
          ) : null}

          <div className="space-y-2" aria-live="polite">
            {transcripts.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-muted/40 px-4 py-5 text-center text-xs text-muted-foreground">
                Live transcripts will appear here while you and Gemini talk.
                {lastTranscript ? null : ''}
              </div>
            ) : (
              transcripts.map((entry, index) => (
                <article
                  key={`${entry.role}-${index}`}
                  className={cn(
                    'rounded-xl border px-3 py-2 text-sm',
                    entry.role === 'user'
                      ? 'border-primary/20 bg-primary/5'
                      : 'border-border bg-muted/40',
                  )}
                >
                  <div className="flex items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    <span>{entry.role === 'assistant' ? 'Gemini Live' : 'You'}</span>
                    <span>{entry.final ? 'final' : 'listening…'}</span>
                  </div>
                  <div className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                    {entry.text}
                  </div>
                </article>
              ))
            )}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})
