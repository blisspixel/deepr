import { io, Socket } from 'socket.io-client'
import type { Job } from '../types'

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
