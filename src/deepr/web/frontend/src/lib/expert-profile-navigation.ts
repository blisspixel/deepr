export const EXPERT_PROFILE_TABS = ['claims', 'gaps', 'decisions', 'history', 'skills', 'chat'] as const

export type ExpertProfileTab = typeof EXPERT_PROFILE_TABS[number]

export function resolveExpertProfileTab(value: string | null): ExpertProfileTab {
  return EXPERT_PROFILE_TABS.find((tab) => tab === value) ?? 'claims'
}

export function localConsultPowerShellCommand(name: string): string {
  const quotedName = `'${name.replace(/'/g, "''")}'`
  return `deepr expert consult 'Your question' --expert=${quotedName} --local`
}
