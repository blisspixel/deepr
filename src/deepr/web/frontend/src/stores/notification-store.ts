import { create } from 'zustand'

interface NotificationState {
  failedJobCount: number
  budgetAlertActive: boolean
  setFailedJobCount: (count: number) => void
  setBudgetAlert: (active: boolean) => void
}

export const useNotificationStore = create<NotificationState>()((set) => ({
  failedJobCount: 0,
  budgetAlertActive: false,

  setFailedJobCount: (count: number) => set({ failedJobCount: count }),
  setBudgetAlert: (active: boolean) => set({ budgetAlertActive: active }),
}))
