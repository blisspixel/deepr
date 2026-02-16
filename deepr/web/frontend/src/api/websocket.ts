import { io, Socket } from 'socket.io-client'
import type { Job, CommandResult, ThoughtItem, PlanStep, ConfirmRequest } from '../types'

const WS_URL = import.meta.env.VITE_WS_URL || `${window.location.protocol}//${window.location.host}`
const isDev = import.meta.env.DEV

class WebSocketClient {
  private socket: Socket | null = null
  private listeners: Map<string, Set<(data: any) => void>> = new Map()
  private _connected = false

  get connected() {
    return this._connected
  }

  connect() {
    if (this.socket?.connected) return

    const token = localStorage.getItem('api_token') || ''
    this.socket = io(WS_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
      auth: token ? { token } : undefined,
    })

    this.socket.on('connect', () => {
      if (isDev) console.log('WebSocket connected')
      this._connected = true
      this.emit('ws_status', { connected: true })
      this.subscribeToJobs()
    })

    this.socket.on('disconnect', () => {
      if (isDev) console.log('WebSocket disconnected')
      this._connected = false
      this.emit('ws_status', { connected: false })
    })

    this.socket.on('connect_error', () => {
      if (isDev) console.warn('WebSocket connection error')
      this._connected = false
      this.emit('ws_status', { connected: false })
    })

    this.socket.on('reconnect_failed' as any, () => {
      if (isDev) console.warn('WebSocket reconnection failed')
      this._connected = false
      this.emit('ws_status', { connected: false })
    })

    this.socket.on('job_created', (job: Job) => {
      this.emit('job_created', job)
    })

    this.socket.on('job_updated', (job: Job) => {
      this.emit('job_updated', job)
    })

    this.socket.on('job_completed', (job: Job) => {
      this.emit('job_completed', job)
    })

    this.socket.on('job_failed', (data: Job & { error?: string }) => {
      this.emit('job_failed', data)
    })

    this.socket.on('cost_warning', (warning: any) => {
      this.emit('cost_warning', warning)
    })

    this.socket.on('cost_exceeded', (exceeded: any) => {
      this.emit('cost_exceeded', exceeded)
    })
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
    this.listeners.clear()
  }

  subscribeToJobs(jobId?: string) {
    if (!this.socket?.connected) return

    const data = jobId ? { scope: 'job', job_id: jobId } : { scope: 'all' }
    this.socket.emit('subscribe_jobs', data)
  }

  unsubscribeFromJobs(jobId?: string) {
    if (!this.socket?.connected) return

    const data = jobId ? { scope: 'job', job_id: jobId } : { scope: 'all' }
    this.socket.emit('unsubscribe_jobs', data)
  }

  startChat(expertName: string, message: string, sessionId?: string, mode?: string) {
    if (!this.socket?.connected) return false
    this.socket.emit('chat_start', {
      expert_name: expertName,
      message,
      ...(sessionId && { session_id: sessionId }),
      ...(mode && { mode }),
    })
    return true
  }

  stopChat() {
    if (!this.socket?.connected) return
    this.socket.emit('chat_stop', {})
  }

  onChatToken(callback: (data: { content: string }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_token', callback)
    return () => { this.socket?.off('chat_token', callback) }
  }

  onChatStatus(callback: (data: { status: string }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_status', callback)
    return () => { this.socket?.off('chat_status', callback) }
  }

  onChatToolStart(callback: (data: { tool: string; query: string }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_tool_start', callback)
    return () => { this.socket?.off('chat_tool_start', callback) }
  }

  onChatToolEnd(callback: (data: { tool: string; elapsed_ms: number }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_tool_end', callback)
    return () => { this.socket?.off('chat_tool_end', callback) }
  }

  onChatComplete(callback: (data: {
    id: string
    content: string
    session_id: string
    cost: number
    tool_calls: { tool: string; query: string }[]
    follow_ups?: string[]
    confidence?: number
  }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_complete', callback)
    return () => { this.socket?.off('chat_complete', callback) }
  }

  onChatError(callback: (data: { error: string }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_error', callback)
    return () => { this.socket?.off('chat_error', callback) }
  }

  // --- Agentic chat events ---

  sendCommand(command: string) {
    if (!this.socket?.connected) return false
    this.socket.emit('chat_command', { command })
    return true
  }

  onCommandResult(callback: (data: CommandResult) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_command_result', callback)
    return () => { this.socket?.off('chat_command_result', callback) }
  }

  onChatThought(callback: (data: ThoughtItem) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_thought', callback)
    return () => { this.socket?.off('chat_thought', callback) }
  }

  sendCompact() {
    if (!this.socket?.connected) return
    this.socket.emit('chat_compact', {})
  }

  onCompactSuggest(callback: (data: { message_count: number; token_estimate: number }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_compact_suggest', callback)
    return () => { this.socket?.off('chat_compact_suggest', callback) }
  }

  onCompactDone(callback: (data: { original_messages?: number; summary_length?: number; error?: string }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_compact_done', callback)
    return () => { this.socket?.off('chat_compact_done', callback) }
  }

  onChatConfirmRequest(callback: (data: ConfirmRequest) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_confirm_request', callback)
    return () => { this.socket?.off('chat_confirm_request', callback) }
  }

  sendConfirmResponse(requestId: string, approved: boolean) {
    if (!this.socket?.connected) return
    this.socket.emit('chat_confirm_response', { request_id: requestId, approved })
  }

  onChatPlan(callback: (data: { query: string; steps: PlanStep[] }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_plan', callback)
    return () => { this.socket?.off('chat_plan', callback) }
  }

  onChatPlanStep(callback: (data: { id: number; title: string; status: string }) => void) {
    if (!this.socket) return () => {}
    this.socket.on('chat_plan_step', callback)
    return () => { this.socket?.off('chat_plan_step', callback) }
  }

  on(event: string, callback: (data: any) => void) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(callback)

    // Return cleanup function
    return () => {
      const callbacks = this.listeners.get(event)
      if (callbacks) {
        callbacks.delete(callback)
        if (callbacks.size === 0) {
          this.listeners.delete(event)
        }
      }
    }
  }

  private emit(event: string, data: any) {
    const callbacks = this.listeners.get(event)
    if (callbacks) {
      callbacks.forEach((callback) => callback(data))
    }
  }
}

export const wsClient = new WebSocketClient()
