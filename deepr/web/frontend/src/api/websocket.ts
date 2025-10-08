import { io, Socket } from 'socket.io-client'
import type { Job } from '../types'

const WS_URL = import.meta.env.VITE_WS_URL || 'http://localhost:5000'

class WebSocketClient {
  private socket: Socket | null = null
  private listeners: Map<string, Set<(data: any) => void>> = new Map()

  connect() {
    if (this.socket?.connected) return

    this.socket = io(WS_URL, {
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 5,
    })

    this.socket.on('connect', () => {
      console.log('WebSocket connected')
      this.subscribeToJobs()
    })

    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected')
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

    this.socket.on('job_failed', (data: { job: Job; error: string }) => {
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
