// api.ts — the browser's calls to the Python Cash backend (mounted at /api on
// the gateway). In dev, Vite proxies /api to the gateway (see vite.config.ts);
// in production the client is served same-origin behind nginx which proxies
// /api. Every call sends the session cookie (credentials: 'include').

export interface ApiResult<T> {
  ok: boolean
  status: number
  data: T
  error?: string
}

export interface ApiOptions {
  signal?: AbortSignal
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export class AcceptedChatJobError extends ApiError {
  readonly accepted = true
  readonly jobId: string
  readonly stillProcessing: boolean

  constructor(message: string, jobId: string, status = 0, stillProcessing = false) {
    super(message, status)
    this.name = 'AcceptedChatJobError'
    this.jobId = jobId
    this.stillProcessing = stillProcessing
  }
}

export async function api<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
  options: ApiOptions = {},
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`/api${path}`, {
      method,
      credentials: 'include',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: options.signal,
    })
    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      data = null
    }
    const errorBody = data as { error?: unknown; detail?: unknown } | null
    const errorCandidate = errorBody?.error || errorBody?.detail
    const error = !res.ok
      ? (typeof errorCandidate === 'string' ? errorCandidate : res.statusText)
      : undefined
    return { ok: res.ok, status: res.status, data: data as T, error }
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    return { ok: false, status: 0, data: null as T, error: (e as Error).message }
  }
}

function requireData<T>(result: ApiResult<T>, fallback: string): T {
  if (!result.ok) throw new ApiError(result.error || fallback, result.status)
  return result.data
}

function parseJson<T>(text: string): T | null {
  if (!text) return null
  try {
    return JSON.parse(text) as T
  } catch {
    return null
  }
}

// --- connectors ---
export interface Connector {
  id: string
  title: string
  available: boolean
  connected: boolean
  unlocks: string[]
  connect_hint: string
}

export async function fetchConnectors(): Promise<Connector[]> {
  const res = await api<{ connectors: Connector[] }>('GET', '/connectors')
  return res.ok ? res.data.connectors : []
}

export async function disconnectConnector(id: string): Promise<boolean> {
  const res = await api<{ disconnected: boolean }>('POST', `/connectors/${id}/disconnect`)
  return res.ok && res.data.disconnected
}

// --- chat ---
export interface ChatResponse {
  reply: string
  action?: string
}

export async function sendChat(message: string): Promise<ChatResponse> {
  const res = await api<ChatResponse>('POST', '/chat', { message })
  const data = requireData(res, 'Cash could not respond right now.')
  if (typeof data.reply !== 'string') throw new ApiError('The chat response was incomplete.', 502)
  return data
}

export interface ChatModel {
  id: string
  displayName: string
  contextWindowTokens: number
  maxOutputTokens: number
  supportsThinking: boolean
  available: boolean
  requiredPlan?: string
}

export interface ChatCapabilities {
  models: ChatModel[]
  defaultModelId: string
  plan: {
    id: string
    label: string
  }
  contextLimitTokens: number
  attachmentLimits: {
    maxFiles: number
    maxBytes: number
    maxImageBytes?: number
    maxPdfPages?: number
    maxTotalBytes?: number
    acceptedTypes: string[]
  }
  voice: {
    enabled: boolean
    maxSeconds: number
    maxBytes: number
    reason?: string
  }
}

export interface ChatContext {
  usedTokens: number
  limitTokens: number
  remainingTokens: number
  estimated: boolean
}

export interface Attachment {
  id: string
  name: string
  mimeType: string
  sizeBytes: number
  status: string
  previewUrl?: string
}

export interface AttachmentStatusResponse {
  attachment: Attachment
}

export async function getChatCapabilities(signal?: AbortSignal): Promise<ChatCapabilities> {
  const res = await api<ChatCapabilities>('GET', '/chat/capabilities', undefined, { signal })
  const data = requireData(res, 'Chat capabilities could not be loaded.')
  if (!Array.isArray(data.models)) throw new ApiError('The model list was incomplete.', 502)
  return data
}

// --- conversations (persistent chat threads, addressed by id) ---
export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  modelId?: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  action?: string
  createdAt: string
  attachments?: Attachment[]
}

export interface ConversationDetail {
  conversation: Conversation
  messages: Message[]
  context: ChatContext
}

export interface SendConversationMessageInput {
  message: string
  modelId: string
  attachmentIds: string[]
  clientRequestId: string
}

export interface SendConversationMessageResponse {
  userMessage: Message
  assistantMessage: Message
  context: ChatContext
  modelId: string
  action?: string
}

interface AcceptedConversationMessageResponse {
  jobId: string
  status: string
  userMessage?: Message
  context?: ChatContext
  modelId?: string
}

interface ConversationMessageJobResponse {
  status: string
  jobId?: string
  attempts?: number
  result?: SendConversationMessageResponse
}

const CHAT_JOB_POLL_TIMEOUT_MS = 180_000
const CHAT_JOB_INITIAL_POLL_DELAY_MS = 700
const CHAT_JOB_MAX_POLL_DELAY_MS = 5_000

function abortError(): DOMException {
  return new DOMException('The request was cancelled.', 'AbortError')
}

function waitFor(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(abortError())
      return
    }

    const timeout = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      window.clearTimeout(timeout)
      signal.removeEventListener('abort', onAbort)
      reject(abortError())
    }
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

function validateConversationMessageResponse(data: unknown): SendConversationMessageResponse {
  const response = data as Partial<SendConversationMessageResponse> | null
  if (
    !response?.userMessage
    || !response.assistantMessage
    || !response.context
    || typeof response.modelId !== 'string'
  ) {
    throw new ApiError('The chat response was incomplete.', 502)
  }
  return response as SendConversationMessageResponse
}

async function pollConversationMessageJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<SendConversationMessageResponse> {
  const controller = new AbortController()
  let timedOut = false
  const forwardAbort = () => controller.abort()
  if (signal?.aborted) forwardAbort()
  else signal?.addEventListener('abort', forwardAbort, { once: true })

  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, CHAT_JOB_POLL_TIMEOUT_MS)

  try {
    let delay = CHAT_JOB_INITIAL_POLL_DELAY_MS
    while (true) {
      await waitFor(delay, controller.signal)
      const response = await api<ConversationMessageJobResponse>(
        'GET',
        `/chat/jobs/${encodeURIComponent(jobId)}`,
        undefined,
        { signal: controller.signal },
      )
      if (!response.ok) {
        throw new AcceptedChatJobError(
          response.error || 'Cash could not load the latest status for this message.',
          jobId,
          response.status,
          response.status === 0,
        )
      }

      const job = response.data
      if (!job || typeof job.status !== 'string') {
        throw new AcceptedChatJobError(
          'The queued message status was incomplete.',
          jobId,
          502,
        )
      }
      if (job.status === 'complete') {
        try {
          return validateConversationMessageResponse(job.result)
        } catch (error) {
          throw new AcceptedChatJobError(
            error instanceof Error ? error.message : 'The completed chat response was incomplete.',
            jobId,
            error instanceof ApiError ? error.status : 502,
          )
        }
      }
      if (job.status === 'failed') {
        throw new AcceptedChatJobError(
          'Cash could not complete this message.',
          jobId,
          502,
        )
      }

      delay = Math.min(
        CHAT_JOB_MAX_POLL_DELAY_MS,
        Math.round(delay * 1.5),
      )
    }
  } catch (error) {
    if (signal?.aborted) throw abortError()
    if (timedOut) {
      throw new AcceptedChatJobError(
        'Cash accepted this message, but its result took longer than expected.',
        jobId,
        408,
        true,
      )
    }
    if (error instanceof AcceptedChatJobError) throw error
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new AcceptedChatJobError(
      error instanceof Error
        ? error.message
        : 'Cash could not load the latest status for this message.',
      jobId,
      error instanceof ApiError ? error.status : 0,
      true,
    )
  } finally {
    window.clearTimeout(timeout)
    signal?.removeEventListener('abort', forwardAbort)
  }
}

export async function listConversations(): Promise<Conversation[]> {
  const res = await api<{ conversations: Conversation[] }>('GET', '/conversations')
  return res.ok ? res.data.conversations : []
}

export async function createConversation(): Promise<Conversation | null> {
  const res = await api<{ conversation: Conversation }>('POST', '/conversations')
  return res.ok ? res.data.conversation : null
}

export async function getConversation(id: string, signal?: AbortSignal): Promise<ConversationDetail> {
  const res = await api<ConversationDetail>('GET', `/conversations/${id}/messages`, undefined, { signal })
  return requireData(res, 'This conversation could not be loaded.')
}

export async function updateConversationModel(
  id: string,
  modelId: string,
  signal?: AbortSignal,
): Promise<void> {
  const res = await api<unknown>('PATCH', `/conversations/${id}`, { modelId }, { signal })
  requireData(res, 'The model preference could not be saved.')
}

export async function sendConversationMessage(
  id: string,
  input: SendConversationMessageInput,
  signal?: AbortSignal,
): Promise<SendConversationMessageResponse> {
  const res = await api<SendConversationMessageResponse | AcceptedConversationMessageResponse>(
    'POST',
    `/conversations/${id}/messages`,
    input,
    { signal },
  )
  const data = requireData(res, 'Your message could not be sent.')
  if (res.status === 202) {
    const jobId = (data as AcceptedConversationMessageResponse)?.jobId
    if (typeof jobId !== 'string' || !jobId) {
      throw new AcceptedChatJobError(
        'Cash accepted this message, but did not return a job identifier.',
        '',
        502,
        true,
      )
    }
    return pollConversationMessageJob(jobId, signal)
  }
  return validateConversationMessageResponse(data)
}

export async function uploadConversationAttachments(
  id: string,
  files: File[],
  {
    signal,
    onProgress,
  }: {
    signal?: AbortSignal
    onProgress?: (percent: number) => void
  } = {},
): Promise<Attachment[]> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file, file.name))

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api/conversations/${encodeURIComponent(id)}/attachments`)
    xhr.withCredentials = true

    const abort = () => xhr.abort()
    signal?.addEventListener('abort', abort, { once: true })

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)))
      }
    }

    xhr.onerror = () => {
      signal?.removeEventListener('abort', abort)
      reject(new ApiError('The attachment upload failed. Check your connection and try again.'))
    }
    xhr.onabort = () => {
      signal?.removeEventListener('abort', abort)
      reject(new DOMException('The attachment upload was cancelled.', 'AbortError'))
    }
    xhr.onload = () => {
      signal?.removeEventListener('abort', abort)
      const data = parseJson<{ attachments?: Attachment[]; error?: string }>(xhr.responseText)
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new ApiError(data?.error || 'The attachment upload failed.', xhr.status))
        return
      }
      if (!Array.isArray(data?.attachments)) {
        reject(new ApiError('The attachment response was incomplete.', 502))
        return
      }
      onProgress?.(100)
      resolve(data.attachments)
    }

    xhr.send(form)
  })
}

export async function getAttachmentStatus(
  id: string,
  signal?: AbortSignal,
): Promise<Attachment> {
  const res = await api<AttachmentStatusResponse>(
    'GET',
    `/attachments/${encodeURIComponent(id)}/status`,
    undefined,
    { signal },
  )
  const data = requireData(res, 'The attachment status could not be loaded.')
  if (
    !data?.attachment
    || data.attachment.id !== id
    || typeof data.attachment.status !== 'string'
  ) {
    throw new ApiError('The attachment status response was incomplete.', 502)
  }
  return data.attachment
}

export async function deleteAttachment(id: string, signal?: AbortSignal): Promise<void> {
  const res = await api<unknown>(
    'DELETE',
    `/attachments/${encodeURIComponent(id)}`,
    undefined,
    { signal },
  )
  requireData(res, 'The attachment could not be removed.')
}

export async function transcribeAudio(
  audio: Blob,
  filename: string,
  signal?: AbortSignal,
): Promise<string> {
  const form = new FormData()
  form.append('audio', audio, filename)
  let response: Response
  try {
    response = await fetch('/api/transcribe', {
      method: 'POST',
      credentials: 'include',
      body: form,
      signal,
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError((error as Error).message || 'Voice transcription failed.')
  }

  const text = await response.text()
  const data = parseJson<{ text?: string; error?: string }>(text)
  if (!response.ok) {
    throw new ApiError(data?.error || response.statusText || 'Voice transcription failed.', response.status)
  }
  if (typeof data?.text !== 'string') throw new ApiError('The transcription response was incomplete.', 502)
  return data.text
}

export async function deleteConversation(id: string): Promise<boolean> {
  const res = await api<{ deleted: boolean }>('DELETE', `/conversations/${id}`)
  return res.ok && res.data.deleted
}
