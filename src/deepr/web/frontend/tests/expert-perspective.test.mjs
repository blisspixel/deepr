import assert from 'node:assert/strict'
import test from 'node:test'
import { expertSourceUrl, expertStudyDate, parseExpertPerspective, parseExpertSources, parseExpertStudy } from '../src/lib/expert-perspective.ts'

test('perspective preserves rationale, dissent and revision conditions without inventing a score', () => {
  const result = parseExpertPerspective({
    orientation: 'A bounded view.', positions: [{ question: 'When?', stance: 'Under this condition.',
      reasoning: 'Because of this mechanism.', unresolved_dissent: 'The alternative has not been measured.',
      would_change_my_mind: 'A contrary measurement.', supported_by: ['mechanism-123'], confidence: 'high' }],
    state: { live: ['A pending investigation.'], unknown: ['A missing measurement.'] },
  })
  assert.equal(result.positions[0].reasoning, 'Because of this mechanism.')
  assert.equal(result.positions[0].unresolved_dissent, 'The alternative has not been measured.')
  assert.deepEqual(result.positions[0].supported_by, ['mechanism-123'])
  assert.equal('confidence' in result.positions[0], false)
  assert.deepEqual(result.state.settled, [])
})

test('corrupt records fail instead of becoming an empty successful study', () => {
  for (const value of [null, [], { positions: 'broken' }, { positions: [null] }]) {
    assert.throws(() => parseExpertPerspective(value))
  }
  assert.throws(() => parseExpertStudy({ outcomes: [{ findings: null }] }))
  assert.throws(() => parseExpertSources({ sources: {} }))
})

test('missing evidence remains missing and superseded source metadata remains resolvable', () => {
  assert.deepEqual(parseExpertPerspective({ positions: [{}] }).positions[0].supported_by, [])
  const study = parseExpertStudy({ started_at: '', outcomes: [{ findings: [{ finding_id: 'a', is_grounded: 'true' }] }] })
  assert.equal(study.findings[0].is_grounded, false)
  assert.deepEqual(study.findings[0].anchors, [])
  assert.equal(parseExpertSources({ sources: [{ sha256: 'old', superseded_by: 'new' }], active: [] })[0].sha256, 'old')
})

test('retained source URLs cannot execute scripts, expose credentials or open local files', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,bad', 'file:///etc/passwd', '//example.com', 'https://user:secret@example.com', 'bad']) {
    assert.equal(expertSourceUrl(value), null)
  }
  assert.equal(expertSourceUrl('https://docs.python.org/3.14/'), 'https://docs.python.org/3.14/')
})

test('study dates stay in UTC and missing dates never become currentness claims', () => {
  assert.equal(expertStudyDate('2026-09-20T00:10:00Z'), 'Sep 20, 2026')
  assert.equal(expertStudyDate(''), null)
  assert.equal(expertStudyDate('unknown'), null)
})
