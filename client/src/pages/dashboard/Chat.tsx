import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useOutletContext, useParams } from 'react-router-dom'
import CashMark from '../../components/CashMark'
import {
  ChevronRightIcon,
  DownloadIcon,
  MicIcon,
  MonitorIcon,
  PaperclipIcon,
  RefreshIcon,
  SendIcon,
  XIcon,
} from '../../components/icons'
import {
  AcceptedChatJobError,
  ApiError,
  deleteAttachment,
  getAttachmentStatus,
  getChatCapabilities,
  getConversation,
  sendConversationMessage,
  transcribeAudio,
  updateConversationModel,
  uploadConversationAttachments,
  type Attachment,
  type ChatCapabilities,
  type ChatContext,
  type ChatModel,
  type Message,
} from '../../lib/api'
import { useAuth } from '../../lib/auth'
import type { DashboardOutletContext } from './Layout'

const STARTERS = [
  "What's on my calendar today?",
  'Remind me to call mom at 6pm',
  'Give me a morning brief',
  'What did I say I wanted to do this week?',
]

type VoiceState = 'idle' | 'requesting' | 'recording' | 'transcribing'
type DeliveryState = 'processing' | 'failed'
type ChatMessage = Message & { deliveryState?: DeliveryState }

interface RetryableDraft {
  clientRequestId: string
  fingerprint: string
}

const ATTACHMENT_STATUS_TIMEOUT_MS = 180_000
const ATTACHMENT_STATUS_INITIAL_DELAY_MS = 900
const ATTACHMENT_STATUS_MAX_DELAY_MS = 4_000

function formatTokens(tokens: number): string {
  const safe = Math.max(0, tokens || 0)
  if (safe >= 1_000_000) return `${(safe / 1_000_000).toFixed(safe >= 10_000_000 ? 0 : 1)}M`
  if (safe >= 1_000) return `${(safe / 1_000).toFixed(safe >= 100_000 ? 0 : 1)}K`
  return safe.toLocaleString()
}

function formatBytes(bytes: number): string {
  const safe = Math.max(0, bytes || 0)
  if (safe >= 1024 * 1024) return `${(safe / (1024 * 1024)).toFixed(safe >= 10 * 1024 * 1024 ? 0 : 1)} MB`
  if (safe >= 1024) return `${Math.round(safe / 1024)} KB`
  return `${safe} B`
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === 'AbortError'
    : error instanceof Error && error.name === 'AbortError'
}

function readableError(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.status === 413) return 'That upload is larger than the allowed limit.'
  if (error instanceof ApiError && error.status === 429) return 'You’re sending requests too quickly. Wait a moment and try again.'
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function newRequestId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `web-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function draftFingerprint(
  conversationId: string,
  message: string,
  modelId: string,
  attachmentIds: string[],
): string {
  return JSON.stringify([conversationId, message, modelId, attachmentIds])
}

function normalizedAttachmentStatus(attachment: Attachment): string {
  return (attachment.status || '').trim().toLowerCase()
}

function isAttachmentReady(attachment: Attachment): boolean {
  return ['ready', 'uploaded'].includes(normalizedAttachmentStatus(attachment))
}

function isAttachmentProcessing(attachment: Attachment): boolean {
  return ['pending', 'processing'].includes(normalizedAttachmentStatus(attachment))
}

function attachmentStatusLabel(attachment: Attachment): string | null {
  const status = normalizedAttachmentStatus(attachment)
  if (status === 'ready' || status === 'uploaded') return null
  if (status === 'pending' || status === 'processing') return 'Processing media…'
  if (status === 'failed') return 'Processing failed'
  if (status === 'processing_timeout') return 'Processing is taking longer'
  if (status === 'status_unavailable') return 'Status unavailable'
  return status ? status.replaceAll('_', ' ') : 'Status unavailable'
}

function waitForAttachmentStatus(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('The status check was cancelled.', 'AbortError'))
      return
    }

    const timeout = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      window.clearTimeout(timeout)
      signal.removeEventListener('abort', onAbort)
      reject(new DOMException('The status check was cancelled.', 'AbortError'))
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

function isAcceptedFile(file: File, acceptedTypes: string[]): boolean {
  if (!acceptedTypes.length || acceptedTypes.includes('*/*')) return true
  const mime = file.type.toLowerCase()
  const name = file.name.toLowerCase()
  return acceptedTypes.some((rawType) => {
    const type = rawType.trim().toLowerCase()
    if (!type) return false
    if (type.startsWith('.')) return name.endsWith(type)
    if (type.endsWith('/*')) return mime.startsWith(type.slice(0, -1))
    return mime === type
  })
}

function bestRecordingMimeType(): string {
  const choices = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']
  return choices.find((type) => MediaRecorder.isTypeSupported(type)) || ''
}

function audioFilename(mimeType: string): string {
  if (mimeType.includes('ogg')) return 'voice-input.ogg'
  if (mimeType.includes('mp4')) return 'voice-input.m4a'
  return 'voice-input.webm'
}

function isPreviewableImage(mimeType: string): boolean {
  return new Set([
    'image/avif',
    'image/gif',
    'image/jpeg',
    'image/png',
    'image/webp',
  ]).has(mimeType.toLowerCase())
}

function AttachmentList({
  attachments,
  removable = false,
  previewFor,
  onRemove,
}: {
  attachments: Attachment[]
  removable?: boolean
  previewFor: (attachment: Attachment) => string | undefined
  onRemove?: (attachment: Attachment) => void
}) {
  if (!attachments.length) return null

  return (
    <div className={`chat-attachments${removable ? ' chat-attachments--pending' : ''}`}>
      {attachments.map((attachment) => {
        const preview = previewFor(attachment)
        const imagePreview = isPreviewableImage(attachment.mimeType) && preview
        const statusLabel = attachmentStatusLabel(attachment)
        return (
          <div className="chat-attachment" key={attachment.id}>
            {imagePreview ? (
              <img src={imagePreview} alt="" className="chat-attachment__preview" />
            ) : (
              <span className="chat-attachment__icon" aria-hidden="true"><PaperclipIcon /></span>
            )}
            <span className="chat-attachment__copy">
              <b title={attachment.name}>{attachment.name}</b>
              <span>
                {formatBytes(attachment.sizeBytes)}
                {statusLabel ? ` · ${statusLabel}` : ''}
              </span>
            </span>
            {removable && onRemove && (
              <button
                type="button"
                className="chat-attachment__remove"
                aria-label={`Remove ${attachment.name}`}
                onClick={() => onRemove(attachment)}
              >
                <XIcon />
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function Chat() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const {
    conversations,
    conversationsLoading,
    refreshConversations,
    startConversation,
  } = useOutletContext<DashboardOutletContext>()

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [booting, setBooting] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [operationError, setOperationError] = useState<string | null>(null)
  const [capabilityError, setCapabilityError] = useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const [capabilities, setCapabilities] = useState<ChatCapabilities | null>(null)
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true)
  const [selectedModelId, setSelectedModelId] = useState('')
  const [savingModel, setSavingModel] = useState(false)
  const [context, setContext] = useState<ChatContext | null>(null)
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([])
  const [uploadingAttachments, setUploadingAttachments] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dragActive, setDragActive] = useState(false)
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [liveStatus, setLiveStatus] = useState('')

  const logRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const activeConversationIdRef = useRef(conversationId)
  const sendControllerRef = useRef<AbortController | null>(null)
  const uploadControllerRef = useRef<AbortController | null>(null)
  const attachmentStatusControllersRef = useRef(new Map<string, AbortController>())
  const pendingAttachmentsConversationIdRef = useRef<string | undefined>(undefined)
  const modelControllerRef = useRef<AbortController | null>(null)
  const transcriptionControllerRef = useRef<AbortController | null>(null)
  const sendRunRef = useRef('')
  const retryableDraftRef = useRef<RetryableDraft | null>(null)
  const draftRevisionRef = useRef(0)
  const attachmentBlockingErrorRef = useRef<string | null>(null)
  const attachmentPreviewsRef = useRef(new Map<string, string>())
  const recorderRef = useRef<MediaRecorder | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const voiceCancelledRef = useRef(false)
  const voiceConversationIdRef = useRef<string | undefined>(undefined)
  const voiceTickerRef = useRef<number | null>(null)
  const voiceLimitTimerRef = useRef<number | null>(null)
  activeConversationIdRef.current = conversationId

  const models = capabilities?.models || []
  const selectedModel = useMemo(
    () => models.find((model) => model.id === selectedModelId),
    [models, selectedModelId],
  )

  const fallbackContextLimit = Math.min(
    capabilities?.contextLimitTokens || Number.MAX_SAFE_INTEGER,
    selectedModel?.contextWindowTokens || Number.MAX_SAFE_INTEGER,
  )
  const contextLimit = context?.limitTokens
    || (Number.isFinite(fallbackContextLimit) ? fallbackContextLimit : 0)
  const contextUsed = Math.max(0, context?.usedTokens || 0)
  const contextRemaining = Math.max(0, context?.remainingTokens ?? (contextLimit - contextUsed))
  const contextPercent = contextLimit ? Math.min(100, Math.round((contextUsed / contextLimit) * 100)) : 0
  const contextEstimated = context?.estimated ?? true
  const planLabel = capabilities?.plan.label || 'Current plan'
  const acceptValue = capabilities?.attachmentLimits.acceptedTypes.join(',') || ''
  const attachmentLimit = capabilities?.attachmentLimits.maxFiles || 0
  const attachmentSizeLimit = capabilities?.attachmentLimits.maxBytes || 0
  const attachmentImageSizeLimit = capabilities?.attachmentLimits.maxImageBytes
    || attachmentSizeLimit
  const attachmentPdfPageLimit = capabilities?.attachmentLimits.maxPdfPages || 0
  const attachmentTotalLimit = capabilities?.attachmentLimits.maxTotalBytes || 0
  const pendingAttachmentBytes = pendingAttachments.reduce(
    (total, attachment) => total + attachment.sizeBytes,
    0,
  )
  const attachmentAvailable = !!capabilities && attachmentLimit > 0
  const attachmentCapacityReached = pendingAttachments.length >= attachmentLimit
    || (attachmentTotalLimit > 0 && pendingAttachmentBytes >= attachmentTotalLimit)
  const processingAttachmentCount = pendingAttachments.filter(isAttachmentProcessing).length
  const blockedAttachmentCount = pendingAttachments.filter(
    (attachment) => !isAttachmentReady(attachment) && !isAttachmentProcessing(attachment),
  ).length
  const attachmentsSendable = pendingAttachments.every(isAttachmentReady)
  const voiceUnavailableMessage = capabilities?.voice.reason === 'not_configured'
    ? 'Voice input isn’t configured for this deployment yet.'
    : `Voice input isn’t available on the ${planLabel} plan.`
  const voiceSupported = typeof MediaRecorder !== 'undefined'
    && !!navigator.mediaDevices?.getUserMedia
  const voiceAvailable = !!capabilities?.voice.enabled && voiceSupported
  const busy = thinking
    || uploadingAttachments
    || processingAttachmentCount > 0
    || voiceState === 'requesting'
    || voiceState === 'transcribing'
  const selectedModelAvailable = !!selectedModelId
    && (!capabilities || selectedModel?.available !== false)
  const canSend = !!conversationId
    && !booting
    && !busy
    && selectedModelAvailable
    && attachmentsSendable
    && (!!input.trim() || pendingAttachments.length > 0)

  function autosize() {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`
  }

  function invalidateRetryableDraft() {
    draftRevisionRef.current += 1
    retryableDraftRef.current = null
  }

  function reportAttachmentBlock(message: string, liveMessage: string) {
    attachmentBlockingErrorRef.current = message
    setOperationError(message)
    setLiveStatus(liveMessage)
  }

  async function pollPendingAttachment(
    attachment: Attachment,
    activeConversationId: string,
    controller: AbortController,
  ) {
    let timedOut = false
    let delay = ATTACHMENT_STATUS_INITIAL_DELAY_MS
    const timeout = window.setTimeout(() => {
      timedOut = true
      controller.abort()
    }, ATTACHMENT_STATUS_TIMEOUT_MS)

    try {
      while (true) {
        await waitForAttachmentStatus(delay, controller.signal)
        if (
          activeConversationIdRef.current !== activeConversationId
          || pendingAttachmentsConversationIdRef.current !== activeConversationId
        ) return

        let updated: Attachment
        try {
          updated = await getAttachmentStatus(attachment.id, controller.signal)
        } catch (error) {
          if (isAbortError(error)) throw error
          if (
            activeConversationIdRef.current !== activeConversationId
            || attachmentStatusControllersRef.current.get(attachment.id) !== controller
          ) return

          const terminalClientError = error instanceof ApiError
            && error.status >= 400
            && error.status < 500
            && error.status !== 429
          if (terminalClientError) {
            setPendingAttachments((current) => current.map((item) => (
              item.id === attachment.id ? { ...item, status: 'status_unavailable' } : item
            )))
            reportAttachmentBlock(
              `${attachment.name} is uploaded, but its processing status could not be checked. Remove it and upload it again.`,
              `${attachment.name} status is unavailable and cannot be sent.`,
            )
            return
          }

          setLiveStatus(`Still processing ${attachment.name}. Retrying the status check.`)
          delay = Math.min(ATTACHMENT_STATUS_MAX_DELAY_MS, Math.round(delay * 1.5))
          continue
        }

        if (
          activeConversationIdRef.current !== activeConversationId
          || attachmentStatusControllersRef.current.get(attachment.id) !== controller
        ) return

        setPendingAttachments((current) => current.map((item) => (
          item.id === attachment.id
            ? {
              ...item,
              ...updated,
              previewUrl: updated.previewUrl || item.previewUrl,
            }
            : item
        )))

        if (isAttachmentReady(updated)) {
          setLiveStatus(`${updated.name} is ready to send.`)
          return
        }
        if (normalizedAttachmentStatus(updated) === 'failed') {
          reportAttachmentBlock(
            `${updated.name} could not be processed. Remove it before sending your message.`,
            `${updated.name} processing failed and it cannot be sent.`,
          )
          return
        }
        if (!isAttachmentProcessing(updated)) {
          setPendingAttachments((current) => current.map((item) => (
            item.id === attachment.id ? { ...item, status: 'status_unavailable' } : item
          )))
          reportAttachmentBlock(
            `${updated.name} returned an unknown processing status. Remove it and upload it again.`,
            `${updated.name} has an unknown status and cannot be sent.`,
          )
          return
        }

        delay = Math.min(ATTACHMENT_STATUS_MAX_DELAY_MS, Math.round(delay * 1.5))
      }
    } catch (error) {
      if (
        !timedOut
        || activeConversationIdRef.current !== activeConversationId
        || attachmentStatusControllersRef.current.get(attachment.id) !== controller
      ) return
      setPendingAttachments((current) => current.map((item) => (
        item.id === attachment.id && isAttachmentProcessing(item)
          ? { ...item, status: 'processing_timeout' }
          : item
      )))
      reportAttachmentBlock(
        `${attachment.name} is taking longer than expected to process. Remove it and try uploading it again.`,
        `${attachment.name} processing timed out and it cannot be sent.`,
      )
    } finally {
      window.clearTimeout(timeout)
      if (attachmentStatusControllersRef.current.get(attachment.id) === controller) {
        attachmentStatusControllersRef.current.delete(attachment.id)
      }
    }
  }

  function previewFor(attachment: Attachment): string | undefined {
    return attachment.previewUrl || attachmentPreviewsRef.current.get(attachment.id)
  }

  function revokeAttachmentPreviews(attachments: Attachment[]) {
    attachments.forEach((attachment) => {
      const preview = attachmentPreviewsRef.current.get(attachment.id)
      if (preview) URL.revokeObjectURL(preview)
      attachmentPreviewsRef.current.delete(attachment.id)
    })
  }

  function revokeAllAttachmentPreviews() {
    attachmentPreviewsRef.current.forEach((preview) => URL.revokeObjectURL(preview))
    attachmentPreviewsRef.current.clear()
  }

  function clearVoiceTimersAndStream() {
    if (voiceTickerRef.current !== null) window.clearInterval(voiceTickerRef.current)
    if (voiceLimitTimerRef.current !== null) window.clearTimeout(voiceLimitTimerRef.current)
    voiceTickerRef.current = null
    voiceLimitTimerRef.current = null
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop())
    mediaStreamRef.current = null
    recorderRef.current = null
  }

  function cancelVoiceRecording() {
    voiceCancelledRef.current = true
    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    else clearVoiceTimersAndStream()
    transcriptionControllerRef.current?.abort()
    transcriptionControllerRef.current = null
    setVoiceState('idle')
    setRecordingSeconds(0)
    setLiveStatus('Voice input cancelled.')
  }

  useEffect(() => {
    const controller = new AbortController()
    setCapabilitiesLoading(true)
    void getChatCapabilities(controller.signal)
      .then((data) => {
        setCapabilities(data)
        setCapabilityError(null)
        setSelectedModelId((current) => current || data.defaultModelId)
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setCapabilityError(readableError(error, 'Models and media options could not be loaded.'))
        }
      })
      .finally(() => setCapabilitiesLoading(false))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (conversationId || conversationsLoading) return

    if (conversations.length > 0) {
      navigate(`/app/chat/${conversations[0].id}`, { replace: true })
      return
    }

    let cancelled = false
    async function createFirstConversation() {
      setBooting(true)
      const conversation = await startConversation()
      if (!conversation && !cancelled) {
        setLoadError('Cash couldn’t start a conversation. Please try again.')
        setBooting(false)
      }
    }
    void createFirstConversation()
    return () => {
      cancelled = true
    }
  }, [
    conversationId,
    conversations,
    conversationsLoading,
    navigate,
    startConversation,
  ])

  useEffect(() => {
    sendControllerRef.current?.abort()
    uploadControllerRef.current?.abort()
    attachmentStatusControllersRef.current.forEach((controller) => controller.abort())
    attachmentStatusControllersRef.current.clear()
    pendingAttachmentsConversationIdRef.current = undefined
    modelControllerRef.current?.abort()
    transcriptionControllerRef.current?.abort()
    retryableDraftRef.current = null
    draftRevisionRef.current += 1
    attachmentBlockingErrorRef.current = null
    if (recorderRef.current || voiceState !== 'idle') cancelVoiceRecording()
    revokeAllAttachmentPreviews()
    setPendingAttachments([])
    setUploadingAttachments(false)
    setUploadProgress(0)
    setThinking(false)
    setSavingModel(false)
    setOperationError(null)
    setDragActive(false)

    if (!conversationId) return
    const activeConversationId = conversationId
    const controller = new AbortController()

    async function loadConversation() {
      setLoadError(null)
      setBooting(true)
      try {
        const data = await getConversation(activeConversationId, controller.signal)
        if (activeConversationIdRef.current !== activeConversationId) return
        setMessages(data.messages)
        setContext(data.context)
        setSelectedModelId(data.conversation.modelId || capabilities?.defaultModelId || '')
      } catch (error) {
        if (isAbortError(error) || activeConversationIdRef.current !== activeConversationId) return
        setMessages([])
        setContext(null)
        setLoadError(readableError(error, 'This conversation couldn’t be loaded. It may no longer be available.'))
      } finally {
        if (activeConversationIdRef.current === activeConversationId) setBooting(false)
      }
    }

    void loadConversation()
    return () => controller.abort()
    // `capabilities` is intentionally not a dependency: a capability refresh
    // must not reload a conversation or overwrite its persisted model.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, retryKey])

  useEffect(() => {
    if (
      !conversationId
      || pendingAttachmentsConversationIdRef.current !== conversationId
    ) return

    const processingIds = new Set(
      pendingAttachments
        .filter(isAttachmentProcessing)
        .map((attachment) => attachment.id),
    )
    attachmentStatusControllersRef.current.forEach((controller, attachmentId) => {
      if (!processingIds.has(attachmentId)) {
        controller.abort()
        attachmentStatusControllersRef.current.delete(attachmentId)
      }
    })

    pendingAttachments.filter(isAttachmentProcessing).forEach((attachment) => {
      if (attachmentStatusControllersRef.current.has(attachment.id)) return
      const controller = new AbortController()
      attachmentStatusControllersRef.current.set(attachment.id, controller)
      void pollPendingAttachment(attachment, conversationId, controller)
    })
  }, [conversationId, pendingAttachments])

  useEffect(() => {
    if (processingAttachmentCount > 0 || blockedAttachmentCount > 0) return
    const attachmentError = attachmentBlockingErrorRef.current
    if (!attachmentError) return
    attachmentBlockingErrorRef.current = null
    setOperationError((current) => current === attachmentError ? null : current)
  }, [blockedAttachmentCount, processingAttachmentCount])

  useEffect(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    logRef.current?.scrollTo({
      top: logRef.current.scrollHeight,
      behavior: reducedMotion ? 'auto' : 'smooth',
    })
  }, [messages, thinking])

  useEffect(() => () => {
    sendControllerRef.current?.abort()
    uploadControllerRef.current?.abort()
    attachmentStatusControllersRef.current.forEach((controller) => controller.abort())
    attachmentStatusControllersRef.current.clear()
    modelControllerRef.current?.abort()
    transcriptionControllerRef.current?.abort()
    voiceCancelledRef.current = true
    if (recorderRef.current && recorderRef.current.state !== 'inactive') recorderRef.current.stop()
    clearVoiceTimersAndStream()
    revokeAllAttachmentPreviews()
  }, [])

  async function changeModel(nextModelId: string) {
    if (!conversationId || nextModelId === selectedModelId) return
    const nextModel = models.find((model) => model.id === nextModelId)
    if (!nextModel?.available) return

    const activeConversationId = conversationId
    const previousModelId = selectedModelId
    const controller = new AbortController()
    invalidateRetryableDraft()
    modelControllerRef.current?.abort()
    modelControllerRef.current = controller
    setSelectedModelId(nextModelId)
    setSavingModel(true)
    setOperationError(null)

    try {
      await updateConversationModel(activeConversationId, nextModelId, controller.signal)
      if (activeConversationIdRef.current !== activeConversationId) return
      const effectiveLimit = Math.min(
        capabilities?.contextLimitTokens || nextModel.contextWindowTokens,
        nextModel.contextWindowTokens,
      )
      setContext((current) => current ? {
        ...current,
        limitTokens: effectiveLimit,
        remainingTokens: Math.max(0, effectiveLimit - current.usedTokens),
        estimated: true,
      } : {
        usedTokens: 0,
        limitTokens: effectiveLimit,
        remainingTokens: effectiveLimit,
        estimated: true,
      })
      setLiveStatus(`${nextModel.displayName} selected.`)
    } catch (error) {
      if (isAbortError(error) || activeConversationIdRef.current !== activeConversationId) return
      setSelectedModelId(previousModelId)
      setOperationError(readableError(error, 'The model preference could not be saved.'))
    } finally {
      if (activeConversationIdRef.current === activeConversationId) setSavingModel(false)
      if (modelControllerRef.current === controller) modelControllerRef.current = null
    }
  }

  async function addFiles(files: File[]) {
    if (!conversationId || !attachmentAvailable || uploadingAttachments || !files.length) return
    const activeConversationId = conversationId
    const limits = capabilities?.attachmentLimits
    if (!limits) return

    const remainingSlots = Math.max(0, limits.maxFiles - pendingAttachments.length)
    const errors: string[] = []
    const selected: File[] = []
    let selectedBytes = pendingAttachmentBytes
    let fileCountExceeded = false

    files.forEach((file) => {
      if (selected.length >= remainingSlots) {
        fileCountExceeded = true
        return
      }
      const fileLimit = file.type.toLowerCase().startsWith('image/')
        ? (limits.maxImageBytes || limits.maxBytes)
        : limits.maxBytes
      if (file.size > fileLimit) {
        errors.push(`${file.name} is over the ${formatBytes(fileLimit)} limit.`)
        return
      }
      if (!isAcceptedFile(file, limits.acceptedTypes)) {
        errors.push(`${file.name} is not a supported file type.`)
        return
      }
      if (limits.maxTotalBytes && selectedBytes + file.size > limits.maxTotalBytes) {
        errors.push(
          `${file.name} would exceed the ${formatBytes(limits.maxTotalBytes)} combined attachment limit.`,
        )
        return
      }
      selected.push(file)
      selectedBytes += file.size
    })

    if (fileCountExceeded) {
      errors.push(`You can attach up to ${limits.maxFiles} files to one message.`)
    }
    if (errors.length) setOperationError(errors.join(' '))
    if (!selected.length) {
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    const controller = new AbortController()
    uploadControllerRef.current?.abort()
    uploadControllerRef.current = controller
    setUploadingAttachments(true)
    setUploadProgress(0)
    if (!errors.length) setOperationError(null)
    setLiveStatus(`Uploading ${selected.length} ${selected.length === 1 ? 'attachment' : 'attachments'}.`)

    try {
      const uploaded = await uploadConversationAttachments(activeConversationId, selected, {
        signal: controller.signal,
        onProgress: setUploadProgress,
      })
      if (activeConversationIdRef.current !== activeConversationId) return
      uploaded.forEach((attachment, index) => {
        const file = selected[index]
        if (file && isPreviewableImage(file.type) && !attachment.previewUrl) {
          attachmentPreviewsRef.current.set(attachment.id, URL.createObjectURL(file))
        }
      })
      invalidateRetryableDraft()
      pendingAttachmentsConversationIdRef.current = activeConversationId
      setPendingAttachments((current) => [...current, ...uploaded])
      const processingCount = uploaded.filter(isAttachmentProcessing).length
      const blockedCount = uploaded.filter(
        (attachment) => !isAttachmentReady(attachment) && !isAttachmentProcessing(attachment),
      ).length
      if (processingCount > 0) {
        setLiveStatus(
          `${processingCount} ${processingCount === 1 ? 'attachment is' : 'attachments are'} processing and cannot be sent yet.`,
        )
      } else if (blockedCount > 0) {
        setLiveStatus(
          `${blockedCount} ${blockedCount === 1 ? 'attachment could' : 'attachments could'} not be prepared for sending.`,
        )
      } else {
        setLiveStatus(`${uploaded.length} ${uploaded.length === 1 ? 'attachment' : 'attachments'} ready.`)
      }
    } catch (error) {
      if (!isAbortError(error) && activeConversationIdRef.current === activeConversationId) {
        setOperationError(readableError(error, 'The attachment upload failed.'))
        setLiveStatus('Attachment upload failed.')
      }
    } finally {
      if (activeConversationIdRef.current === activeConversationId) {
        setUploadingAttachments(false)
        setUploadProgress(0)
      }
      if (uploadControllerRef.current === controller) uploadControllerRef.current = null
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function removeAttachment(attachment: Attachment) {
    const activeConversationId = conversationId
    invalidateRetryableDraft()
    attachmentStatusControllersRef.current.get(attachment.id)?.abort()
    attachmentStatusControllersRef.current.delete(attachment.id)
    revokeAttachmentPreviews([attachment])
    setPendingAttachments((current) => current.filter((item) => item.id !== attachment.id))
    setLiveStatus(`${attachment.name} removed.`)

    try {
      await deleteAttachment(attachment.id)
    } catch (error) {
      if (activeConversationIdRef.current !== activeConversationId) return
      setOperationError(
        `${attachment.name} was removed from this draft, but its upload could not be deleted. ${readableError(error, 'Try again later.')}`,
      )
      setLiveStatus(`${attachment.name} was removed, but upload cleanup failed.`)
    }
  }

  async function startVoiceRecording() {
    if (!capabilities?.voice.enabled) {
      setOperationError(voiceUnavailableMessage)
      return
    }
    if (!voiceSupported) {
      setOperationError('Voice input is not supported in this browser.')
      return
    }
    if (!conversationId || voiceState !== 'idle') return

    const activeConversationId = conversationId
    setVoiceState('requesting')
    setOperationError(null)
    setLiveStatus('Requesting microphone access.')
    voiceCancelledRef.current = false
    voiceConversationIdRef.current = activeConversationId

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          autoGainControl: true,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      if (activeConversationIdRef.current !== activeConversationId || voiceCancelledRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }

      const mimeType = bestRecordingMimeType()
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      const chunks: BlobPart[] = []
      mediaStreamRef.current = stream
      recorderRef.current = recorder

      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data)
      }
      recorder.onerror = () => {
        clearVoiceTimersAndStream()
        if (activeConversationIdRef.current !== activeConversationId) return
        setVoiceState('idle')
        setRecordingSeconds(0)
        setOperationError('The recording stopped unexpectedly. Please try again.')
      }
      recorder.onstop = async () => {
        const cancelled = voiceCancelledRef.current
        const recordingConversationId = voiceConversationIdRef.current
        const recordedType = recorder.mimeType || mimeType || 'audio/webm'
        clearVoiceTimersAndStream()
        setRecordingSeconds(0)
        if (cancelled) {
          setVoiceState('idle')
          return
        }

        const audio = new Blob(chunks, { type: recordedType })
        if (!audio.size) {
          setVoiceState('idle')
          setOperationError('No audio was captured. Check your microphone and try again.')
          return
        }
        if (audio.size > capabilities.voice.maxBytes) {
          setVoiceState('idle')
          setOperationError(`That recording is over the ${formatBytes(capabilities.voice.maxBytes)} limit.`)
          return
        }

        const controller = new AbortController()
        transcriptionControllerRef.current = controller
        setVoiceState('transcribing')
        setLiveStatus('Transcribing voice input.')
        try {
          const transcript = (await transcribeAudio(
            audio,
            audioFilename(recordedType),
            controller.signal,
          )).trim()
          if (activeConversationIdRef.current !== recordingConversationId) return
          if (!transcript) {
            setOperationError('Cash couldn’t hear any speech in that recording.')
            return
          }
          invalidateRetryableDraft()
          setInput((current) => current.trim() ? `${current.trim()} ${transcript}` : transcript)
          setLiveStatus('Voice input added to the composer.')
          requestAnimationFrame(() => {
            autosize()
            textareaRef.current?.focus()
          })
        } catch (error) {
          if (!isAbortError(error) && activeConversationIdRef.current === recordingConversationId) {
            setOperationError(readableError(error, 'Voice transcription failed.'))
            setLiveStatus('Voice transcription failed.')
          }
        } finally {
          if (activeConversationIdRef.current === recordingConversationId) setVoiceState('idle')
          if (transcriptionControllerRef.current === controller) transcriptionControllerRef.current = null
        }
      }

      const startedAt = Date.now()
      recorder.start(250)
      setRecordingSeconds(0)
      setVoiceState('recording')
      setLiveStatus('Recording voice input.')
      voiceTickerRef.current = window.setInterval(() => {
        setRecordingSeconds(Math.floor((Date.now() - startedAt) / 1000))
      }, 500)
      voiceLimitTimerRef.current = window.setTimeout(() => {
        if (recorder.state === 'recording') recorder.stop()
      }, capabilities.voice.maxSeconds * 1000)
    } catch (error) {
      clearVoiceTimersAndStream()
      if (activeConversationIdRef.current !== activeConversationId || voiceCancelledRef.current) return
      setVoiceState('idle')
      if ((error as DOMException).name === 'NotAllowedError') {
        setOperationError('Microphone access was blocked. Allow access in your browser settings and try again.')
      } else {
        setOperationError(readableError(error, 'Cash couldn’t access your microphone.'))
      }
      setLiveStatus('Microphone access failed.')
    }
  }

  function stopAndTranscribeVoice() {
    const recorder = recorderRef.current
    if (recorder?.state === 'recording') recorder.stop()
  }

  async function send() {
    const text = input.trim()
    if ((!text && !pendingAttachments.length) || !conversationId) return
    const processingCount = pendingAttachments.filter(isAttachmentProcessing).length
    if (!pendingAttachments.every(isAttachmentReady)) {
      const message = processingCount > 0
        ? `Wait for ${processingCount === 1 ? 'the attachment' : 'all attachments'} to finish processing before sending.`
        : 'Remove attachments that could not be processed before sending.'
      reportAttachmentBlock(message, message)
      return
    }
    if (!canSend) return

    const activeConversationId = conversationId
    const attachmentIds = pendingAttachments.map((attachment) => attachment.id)
    const fingerprint = draftFingerprint(
      activeConversationId,
      text,
      selectedModelId,
      attachmentIds,
    )
    const retryableDraft = retryableDraftRef.current
    const requestId = retryableDraft?.fingerprint === fingerprint
      ? retryableDraft.clientRequestId
      : newRequestId()
    const temporaryId = `pending-${requestId}`
    const sentAttachments = pendingAttachments
    const sentDraftRevision = draftRevisionRef.current
    const controller = new AbortController()
    retryableDraftRef.current = null
    sendControllerRef.current?.abort()
    sendControllerRef.current = controller
    sendRunRef.current = requestId

    setInput('')
    setPendingAttachments([])
    setOperationError(null)
    requestAnimationFrame(autosize)
    setMessages((current) => [
      ...current,
      {
        id: temporaryId,
        role: 'user',
        content: text,
        attachments: sentAttachments,
        createdAt: new Date().toISOString(),
      },
    ])
    setThinking(true)
    setLiveStatus('Message sending. Cash is thinking.')

    try {
      const response = await sendConversationMessage(activeConversationId, {
        message: text,
        modelId: selectedModelId,
        attachmentIds,
        clientRequestId: requestId,
      }, controller.signal)
      if (activeConversationIdRef.current !== activeConversationId) return

      setMessages((current) => {
        const pendingIndex = current.findIndex((message) => message.id === temporaryId)
        if (pendingIndex === -1) return current
        return [
          ...current.slice(0, pendingIndex),
          response.userMessage,
          response.assistantMessage,
          ...current.slice(pendingIndex + 1),
        ]
      })
      setContext(response.context)
      setSelectedModelId(response.modelId)
      revokeAttachmentPreviews(sentAttachments)
      setLiveStatus(response.assistantMessage.content || 'Cash responded.')
      void refreshConversations()
    } catch (error) {
      if (isAbortError(error) || activeConversationIdRef.current !== activeConversationId) return
      if (error instanceof AcceptedChatJobError) {
        retryableDraftRef.current = null
        setMessages((current) => current.map((message) => (
          message.id === temporaryId
            ? {
              ...message,
              deliveryState: error.stillProcessing ? 'processing' : 'failed',
            }
            : message
        )))
        setOperationError(
          error.stillProcessing
            ? 'Cash accepted this message and may still be processing it. Reopen or refresh this conversation to see the latest result.'
            : `${readableError(error, 'Cash could not finish this message.')} This turn was accepted, so reopen the conversation to refresh its status before sending a new turn.`,
        )
        setLiveStatus(
          error.stillProcessing
            ? 'Message accepted and still processing. Reopen the conversation to refresh.'
            : 'Message accepted, but processing did not complete. Reopen the conversation to refresh.',
        )
        void refreshConversations()
        return
      }

      setMessages((current) => current.filter((message) => message.id !== temporaryId))
      if (draftRevisionRef.current === sentDraftRevision) {
        retryableDraftRef.current = { clientRequestId: requestId, fingerprint }
      } else {
        retryableDraftRef.current = null
      }
      setInput((current) => [text, current].filter((part) => part.trim()).join('\n'))
      setPendingAttachments((current) => [
        ...sentAttachments,
        ...current.filter((attachment) => !sentAttachments.some((sent) => sent.id === attachment.id)),
      ])
      setOperationError(readableError(error, 'Your message didn’t send. Your draft is still here.'))
      setLiveStatus('Message failed to send. Your draft was restored.')
      requestAnimationFrame(autosize)
    } finally {
      if (sendRunRef.current === requestId && activeConversationIdRef.current === activeConversationId) {
        setThinking(false)
        requestAnimationFrame(() => textareaRef.current?.focus())
      }
      if (sendControllerRef.current === controller) sendControllerRef.current = null
    }
  }

  function chooseStarter(starter: string) {
    invalidateRetryableDraft()
    setInput(starter)
    requestAnimationFrame(() => {
      autosize()
      textareaRef.current?.focus()
    })
  }

  const empty = messages.length === 0 && !thinking
  const firstName = user?.profile.firstName || 'there'
  const shownError = operationError || capabilityError
  const modelHelp = selectedModel
    ? `${selectedModel.displayName} supports up to ${formatTokens(selectedModel.contextWindowTokens)} tokens.`
    : 'Choose the model Cash will use for this conversation.'
  const attachTitle = capabilitiesLoading
    ? 'Loading attachment options'
    : !attachmentAvailable
      ? `Attachments aren’t available on the ${planLabel} plan`
      : pendingAttachments.length >= attachmentLimit
        ? `You can attach up to ${attachmentLimit} files`
        : attachmentTotalLimit > 0 && pendingAttachmentBytes >= attachmentTotalLimit
          ? `Combined attachment limit reached (${formatBytes(attachmentTotalLimit)})`
          : `Attach up to ${attachmentLimit} files, ${formatBytes(attachmentSizeLimit)} each${
            attachmentImageSizeLimit < attachmentSizeLimit
              ? ` (${formatBytes(attachmentImageSizeLimit)} for images)`
              : ''
          }${attachmentPdfPageLimit > 0 ? `, ${attachmentPdfPageLimit}-page PDFs` : ''}${
            attachmentTotalLimit > 0 ? `, ${formatBytes(attachmentTotalLimit)} total` : ''
          }`
  const voiceTitle = capabilitiesLoading
    ? 'Loading voice options'
    : !capabilities?.voice.enabled
      ? voiceUnavailableMessage
      : !voiceSupported
        ? 'Voice input is not supported in this browser'
        : voiceState === 'recording'
          ? 'Stop and transcribe recording'
          : 'Use voice input'
  const sendTitle = thinking
    ? 'Cash is responding'
    : uploadingAttachments
      ? 'Wait for attachments to finish uploading'
      : processingAttachmentCount > 0
        ? `Wait for ${processingAttachmentCount === 1 ? 'the attachment' : 'all attachments'} to finish processing`
        : blockedAttachmentCount > 0
          ? 'Remove attachments that could not be processed before sending'
          : voiceState === 'requesting' || voiceState === 'transcribing'
            ? 'Finish voice input before sending'
            : 'Send message'

  return (
    <section className="chat" aria-label="Chat with Cash" aria-busy={busy || booting}>
      <p className="sr-only" aria-live="polite" aria-atomic="true">{liveStatus}</p>

      {shownError && (
        <div className="chat-inline-error status-banner status-banner--error status-banner--dismissible" role="alert">
          <span>{shownError}</span>
          <button
            type="button"
            className="icon-button"
            aria-label="Dismiss message"
            onClick={() => {
              setOperationError(null)
              setCapabilityError(null)
            }}
          >
            <XIcon />
          </button>
        </div>
      )}

      <div className="chat-log" ref={logRef} role="log" aria-label="Conversation messages">
        {booting ? (
          <div className="chat-loading" role="status">
            <span className="spinner" aria-hidden="true" />
            <span>Loading conversation…</span>
          </div>
        ) : loadError && messages.length === 0 ? (
          <div className="state-panel state-panel--chat">
            <span className="state-panel__icon"><RefreshIcon /></span>
            <h2>Conversation unavailable</h2>
            <p>{loadError}</p>
            <button type="button" className="btn btn-primary" onClick={() => setRetryKey((current) => current + 1)}>
              <RefreshIcon /> Try again
            </button>
          </div>
        ) : empty ? (
          <div className="chat-greeting">
            <div className="chat-breadcrumb">
              <span>Thinking</span>
              <ChevronRightIcon />
            </div>
            <div className="chat-greeting__intro">
              <span className="chat-greeting__mark" aria-hidden="true"><CashMark /></span>
              <h1>Hey {firstName} — I’m <span className="cash-name">Cash</span></h1>
            </div>
            <p>
              I’m here to help with planning, research, managing your inbox and calendar,
              or simply thinking something through. What are you working on?
            </p>
            <div className="starters" aria-label="Suggested prompts">
              {STARTERS.map((starter) => (
                <button type="button" key={starter} className="starter" onClick={() => chooseStarter(starter)}>
                  {starter}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-thread">
            <div className="chat-breadcrumb">
              <span>Thinking</span>
              <ChevronRightIcon />
            </div>
            {messages.map((message) => (
              <article key={message.id} className={`turn ${message.role}`}>
                <span className="avatar" aria-hidden="true">
                  {message.role === 'assistant' ? <CashMark /> : (user?.profile.firstName?.[0]?.toUpperCase() || 'Y')}
                </span>
                <div className="turn-body">
                  {!!message.content && <div className="content">{message.content}</div>}
                  <AttachmentList attachments={message.attachments || []} previewFor={previewFor} />
                  {message.deliveryState && (
                    <span className={`turn-delivery-status turn-delivery-status--${message.deliveryState}`} role="status">
                      {message.deliveryState === 'processing'
                        ? 'Still processing · Reopen this conversation to refresh'
                        : 'Processing did not complete · Reopen this conversation to refresh'}
                    </span>
                  )}
                </div>
              </article>
            ))}
            {thinking && (
              <div className="turn assistant">
                <span className="avatar" aria-hidden="true"><CashMark /></span>
                <div className="content typing" role="status" aria-label="Cash is thinking">
                  <span /><span /><span />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="composer-wrap">
        <div className="desktop-promo">
          <span className="desktop-promo__icon" aria-hidden="true"><MonitorIcon /></span>
          <span className="desktop-promo__copy">
            <b>Get the desktop app</b>
            <span>Computer access · faster workflows · native automation</span>
          </span>
          <button type="button" className="btn btn-primary btn-small" disabled title="Desktop app coming soon">
            <DownloadIcon /> Coming soon
          </button>
        </div>

        <div className="composer-settings">
          <label className="chat-model-control">
            <span className="chat-model-control__label">
              <span>Model</span>
              {savingModel && <span className="spinner spinner--button" aria-hidden="true" />}
            </span>
            <select
              value={selectedModelId}
              disabled={booting || thinking || savingModel || capabilitiesLoading || !conversationId}
              aria-describedby="chat-model-help"
              onChange={(event) => void changeModel(event.target.value)}
            >
              {!selectedModelId && <option value="">Select a model</option>}
              {!!selectedModelId && !models.some((model) => model.id === selectedModelId) && (
                <option value={selectedModelId}>Current model</option>
              )}
              {models.map((model: ChatModel) => (
                <option key={model.id} value={model.id} disabled={!model.available}>
                  {model.displayName}
                  {!model.available
                    ? ` — ${model.requiredPlan ? `${model.requiredPlan} required` : 'unavailable'}`
                    : model.supportsThinking ? ' · Thinking' : ''}
                </option>
              ))}
              {capabilitiesLoading && <option value="">Loading models…</option>}
            </select>
            <span className="sr-only" id="chat-model-help">{modelHelp}</span>
          </label>

          <div className="chat-context-usage" id="composer-context">
            <div className="chat-context-usage__copy" id="composer-context-copy">
              <span>{planLabel} context</span>
              <span>
                {formatTokens(contextUsed)} / {formatTokens(contextLimit)}
                {contextEstimated ? ' estimated' : ''}
              </span>
            </div>
            <div
              className="chat-context-meter"
              role="progressbar"
              aria-label={`${planLabel} context used`}
              aria-valuemin={0}
              aria-valuemax={contextLimit || 1}
              aria-valuenow={Math.min(contextUsed, contextLimit || 1)}
              aria-valuetext={`${formatTokens(contextUsed)} of ${formatTokens(contextLimit)} tokens used; ${formatTokens(contextRemaining)} remaining${contextEstimated ? ', estimated' : ''}`}
              title={`${formatTokens(contextRemaining)} tokens remaining${contextEstimated ? ' (estimated)' : ''}`}
            >
              <span style={{ width: `${contextPercent}%` }} />
            </div>
          </div>
        </div>

        <form
          className="composer"
          aria-label="Message Cash"
          onSubmit={(event) => {
            event.preventDefault()
            void send()
          }}
        >
          <div
            className={`composer-field${dragActive ? ' is-dragging' : ''}`}
            onDragEnter={(event) => {
              event.preventDefault()
              if (attachmentAvailable) setDragActive(true)
            }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={(event) => {
              const nextTarget = event.relatedTarget
              if (!(nextTarget instanceof Node) || !event.currentTarget.contains(nextTarget)) {
                setDragActive(false)
              }
            }}
            onDrop={(event) => {
              event.preventDefault()
              setDragActive(false)
              void addFiles(Array.from(event.dataTransfer.files))
            }}
          >
            {pendingAttachments.length > 0 && (
              <div className="composer-attachment-summary">
                <span>Attachments</span>
                <span>
                  {pendingAttachments.length}/{attachmentLimit} files · {formatBytes(pendingAttachmentBytes)}
                  {attachmentTotalLimit > 0 ? ` / ${formatBytes(attachmentTotalLimit)}` : ''}
                  {processingAttachmentCount > 0
                    ? ` · ${processingAttachmentCount} processing`
                    : blockedAttachmentCount > 0
                      ? ` · ${blockedAttachmentCount} unavailable`
                      : ''}
                </span>
              </div>
            )}

            <AttachmentList
              attachments={pendingAttachments}
              removable
              previewFor={previewFor}
              onRemove={removeAttachment}
            />

            {uploadingAttachments && (
              <div className="composer-upload" role="status">
                <span>Uploading attachments…</span>
                <div
                  className="composer-upload__meter"
                  role="progressbar"
                  aria-label="Attachment upload progress"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={uploadProgress}
                >
                  <span style={{ width: `${uploadProgress}%` }} />
                </div>
                <span>{uploadProgress}%</span>
              </div>
            )}

            {voiceState !== 'idle' && (
              <div className={`voice-recorder voice-recorder--${voiceState}`} role="status">
                {voiceState === 'recording' ? (
                  <>
                    <span className="voice-recorder__pulse" aria-hidden="true" />
                    <span className="voice-recorder__copy">
                      Recording {formatDuration(recordingSeconds)}
                      <span> / {formatDuration(capabilities?.voice.maxSeconds || 0)}</span>
                    </span>
                    <button type="button" className="voice-recorder__stop" onClick={stopAndTranscribeVoice}>
                      Stop &amp; transcribe
                    </button>
                    <button
                      type="button"
                      className="chat-attachment__remove"
                      aria-label="Cancel voice recording"
                      onClick={cancelVoiceRecording}
                    >
                      <XIcon />
                    </button>
                  </>
                ) : (
                  <>
                    <span className="spinner spinner--button" aria-hidden="true" />
                    <span>{voiceState === 'requesting' ? 'Opening microphone…' : 'Transcribing voice input…'}</span>
                  </>
                )}
              </div>
            )}

            <label className="sr-only" htmlFor="chat-message">Message Cash</label>
            <textarea
              id="chat-message"
              name="message"
              ref={textareaRef}
              value={input}
              rows={1}
              wrap="soft"
              placeholder={pendingAttachments.length ? 'Add a message or send the attachments…' : 'What are you working on?'}
              disabled={booting || !conversationId}
              aria-describedby="composer-hint composer-context-copy"
              onChange={(event) => {
                invalidateRetryableDraft()
                setInput(event.target.value)
                autosize()
              }}
              onKeyDown={(event) => {
                if (event.nativeEvent.isComposing || event.keyCode === 229) return
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void send()
                }
              }}
            />
            <div className="composer-footer">
              <div className="composer-mode" id="composer-hint">
                <span className="composer-cash-mark" aria-hidden="true"><CashMark /></span>
                <span>{selectedModel?.displayName || 'Select a model'}</span>
                <span className="composer-shortcut">· Enter to send</span>
              </div>
              <div className="composer-actions">
                <input
                  ref={fileInputRef}
                  className="sr-only"
                  type="file"
                  multiple
                  accept={acceptValue}
                  tabIndex={-1}
                  aria-label="Choose files to attach"
                  onChange={(event) => void addFiles(Array.from(event.target.files || []))}
                />
                <button
                  type="button"
                  className={`composer-action${!attachmentAvailable || attachmentCapacityReached ? ' is-disabled' : ''}`}
                  aria-label="Attach files"
                  aria-disabled={!attachmentAvailable || uploadingAttachments || attachmentCapacityReached}
                  title={attachTitle}
                  onClick={() => {
                    if (attachmentAvailable && !uploadingAttachments && !attachmentCapacityReached) {
                      fileInputRef.current?.click()
                    }
                  }}
                >
                  {uploadingAttachments
                    ? <span className="spinner spinner--button" aria-hidden="true" />
                    : <PaperclipIcon />}
                </button>
                <button
                  type="button"
                  className={`composer-action${voiceState === 'recording' ? ' is-recording' : ''}${!voiceAvailable ? ' is-disabled' : ''}`}
                  aria-label={voiceState === 'recording' ? 'Stop and transcribe voice input' : voiceTitle}
                  aria-pressed={voiceState === 'recording'}
                  aria-disabled={!voiceAvailable || voiceState === 'requesting' || voiceState === 'transcribing'}
                  title={voiceTitle}
                  onClick={() => {
                    if (voiceState === 'recording') stopAndTranscribeVoice()
                    else void startVoiceRecording()
                  }}
                >
                  {voiceState === 'requesting' || voiceState === 'transcribing'
                    ? <span className="spinner spinner--button" aria-hidden="true" />
                    : <MicIcon />}
                </button>
                <button
                  type="submit"
                  className="send-btn"
                  disabled={!canSend}
                  aria-label={sendTitle}
                  title={sendTitle}
                >
                  {thinking ? <span className="spinner spinner--button" aria-hidden="true" /> : <SendIcon />}
                </button>
              </div>
            </div>
          </div>
        </form>
      </div>
    </section>
  )
}
