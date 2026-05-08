import { describe, expect, it } from 'bun:test'

import {
  finalizeLatestTranscript,
  mergeAssistantCumulativeText,
  mergeUserDeltaText,
  updateTranscriptList,
  type TranscriptEntry,
} from '../transcript'

describe('mergeUserDeltaText', () => {
  it('returns the non-empty value when one side is blank', () => {
    expect(mergeUserDeltaText('', 'hello')).toBe('hello')
    expect(mergeUserDeltaText('hello', '')).toBe('hello')
  })

  it('dedupes a realistic overlap at the boundary', () => {
    expect(mergeUserDeltaText('hello world to', 'world tour starts')).toBe(
      'hello world tour starts',
    )
  })

  it('keeps the superset when one contains the other', () => {
    expect(mergeUserDeltaText('hello', 'hello world')).toBe('hello world')
    expect(mergeUserDeltaText('hello world', 'world')).toBe('hello world')
  })

  it('falls back to joining with a space', () => {
    expect(mergeUserDeltaText('alpha', 'beta')).toBe('alpha beta')
  })
})

describe('mergeAssistantCumulativeText', () => {
  it('prefers the longer cumulative string', () => {
    expect(mergeAssistantCumulativeText('Hello', 'Hello there')).toBe('Hello there')
  })

  it('does not duplicate when the same string is re-emitted', () => {
    expect(mergeAssistantCumulativeText('Hi there', 'Hi there')).toBe('Hi there')
  })

  it('ignores strictly shorter substrings (stale late deltas)', () => {
    expect(mergeAssistantCumulativeText('Hi there friend', 'Hi')).toBe('Hi there friend')
  })

  it('falls back to overlap merge when a shorter divergent delta arrives', () => {
    // previous is longer than next and they diverge: merge with overlap dedupe.
    expect(
      mergeAssistantCumulativeText('hello world tour start', 'tour starts now'),
    ).toBe('hello world tour starts now')
  })
})

describe('updateTranscriptList', () => {
  it('appends when the last entry is final', () => {
    const current: TranscriptEntry[] = [
      { role: 'user', text: 'hi', final: true },
    ]
    const next = updateTranscriptList(current, {
      role: 'assistant',
      text: 'hello',
      final: false,
    })
    expect(next).toHaveLength(2)
    expect(next[1]).toEqual({ role: 'assistant', text: 'hello', final: false })
  })

  it('folds non-final assistant chunks using cumulative merge', () => {
    let transcripts: TranscriptEntry[] = []
    transcripts = updateTranscriptList(transcripts, {
      role: 'assistant',
      text: 'Hi',
      final: false,
    })
    transcripts = updateTranscriptList(transcripts, {
      role: 'assistant',
      text: 'Hi there',
      final: false,
    })
    transcripts = updateTranscriptList(transcripts, {
      role: 'assistant',
      text: 'Hi there friend',
      final: false,
    })
    expect(transcripts).toHaveLength(1)
    expect(transcripts[0].text).toBe('Hi there friend')
  })

  it('folds non-final user chunks using delta merge', () => {
    let transcripts: TranscriptEntry[] = []
    transcripts = updateTranscriptList(transcripts, {
      role: 'user',
      text: 'hello world to',
      final: false,
    })
    transcripts = updateTranscriptList(transcripts, {
      role: 'user',
      text: 'world tour starts',
      final: false,
    })
    expect(transcripts).toHaveLength(1)
    expect(transcripts[0].text).toBe('hello world tour starts')
  })

  it('does not duplicate the assistant running transcript on re-emission', () => {
    let transcripts: TranscriptEntry[] = []
    for (let i = 0; i < 5; i += 1) {
      transcripts = updateTranscriptList(transcripts, {
        role: 'assistant',
        text: 'Gemini response',
        final: false,
      })
    }
    expect(transcripts).toHaveLength(1)
    expect(transcripts[0].text).toBe('Gemini response')
  })
})

describe('finalizeLatestTranscript', () => {
  it('finalizes the last non-final entry when no role is specified', () => {
    const result = finalizeLatestTranscript([
      { role: 'user', text: 'hi', final: true },
      { role: 'assistant', text: 'hello', final: false },
    ])
    expect(result[1].final).toBe(true)
  })

  it('skips entries whose role does not match', () => {
    const result = finalizeLatestTranscript(
      [
        { role: 'user', text: 'hi', final: false },
        { role: 'assistant', text: 'hello', final: false },
      ],
      'user',
    )
    expect(result[0].final).toBe(true)
    expect(result[1].final).toBe(false)
  })
})
