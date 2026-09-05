import assert from 'node:assert/strict'
import test from 'node:test'
import { localConsultPowerShellCommand, resolveExpertProfileTab } from '../src/lib/expert-profile-navigation.ts'

test('new and invalid profile routes open retained claims', () => {
  for (const value of [null, '', 'unknown', 'Claims', '__proto__']) {
    assert.equal(resolveExpertProfileTab(value), 'claims')
  }
})

test('explicit profile destinations preserve saved chat and evidence navigation', () => {
  for (const value of ['claims', 'gaps', 'decisions', 'history', 'skills', 'chat']) {
    assert.equal(resolveExpertProfileTab(value), value)
  }
})

test('local consultation names remain literal PowerShell arguments', () => {
  assert.equal(
    localConsultPowerShellCommand("Researcher's $notes ` & $(example)"),
    "deepr expert consult 'Your question' --expert='Researcher''s $notes ` & $(example)' --local",
  )
  assert.equal(
    localConsultPowerShellCommand('-option-like name'),
    "deepr expert consult 'Your question' --expert='-option-like name' --local",
  )
})
