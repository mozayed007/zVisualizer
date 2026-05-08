export type TranscriptRole = 'user' | 'assistant'

export interface TranscriptEntry {
  role: TranscriptRole
  text: string
  final: boolean
}

/**
 * Merge two pieces of user-side transcript text with overlap dedupe.
 * Gemini Live emits user-side ASR in deltas that occasionally overlap when
 * the backend re-emits a confirmed chunk — dedupe with a short overlap window.
 */
export function mergeUserDeltaText(previousText: string, nextText: string): string {
  const previous = previousText.trim()
  const next = nextText.trim()
  if (!previous) return next
  if (!next) return previous

  // If one string fully contains the other, keep the longer / more recent one.
  if (next.includes(previous)) return next
  if (previous.includes(next)) return previous

  const overlapLength = Math.min(previous.length, next.length, 48)
  for (let size = overlapLength; size >= 6; size -= 1) {
    if (previous.slice(-size).toLowerCase() === next.slice(0, size).toLowerCase()) {
      return `${previous}${next.slice(size)}`
    }
  }
  return `${previous} ${next}`
}

/**
 * Given the latest cumulative assistant transcript, pick the string that
 * best represents the running turn. Gemini Live's assistant transcripts are
 * typically cumulative, so we treat `next` as authoritative when it is longer
 * than or a superset of `previous`. Otherwise we keep the current text to
 * avoid flicker when a stale delta arrives late.
 */
export function mergeAssistantCumulativeText(previousText: string, nextText: string): string {
  const previous = previousText
  const next = nextText
  if (!previous) return next
  if (!next) return previous
  if (next.length >= previous.length) return next
  // If `next` is a strict prefix/suffix of `previous`, keep `previous`.
  if (previous.includes(next)) return previous
  // Otherwise treat `next` as a new tail and overlap-merge.
  return mergeUserDeltaText(previous, next)
}

/**
 * Append or fold a new transcript chunk into the running transcript list.
 * Consecutive non-final chunks from the same role collapse into a single entry.
 */
export function updateTranscriptList(
  current: TranscriptEntry[],
  nextEntry: TranscriptEntry,
): TranscriptEntry[] {
  const last = current[current.length - 1]
  if (last && last.role === nextEntry.role && !last.final) {
    const mergedText =
      nextEntry.role === 'assistant'
        ? mergeAssistantCumulativeText(last.text, nextEntry.text)
        : mergeUserDeltaText(last.text, nextEntry.text)
    return [
      ...current.slice(0, -1),
      {
        role: nextEntry.role,
        text: mergedText,
        final: nextEntry.final,
      },
    ]
  }
  return [...current, nextEntry]
}

/**
 * Mark the most-recent non-final transcript entry (optionally matching a role)
 * as final. Used when Gemini Live signals `turn.complete`.
 */
export function finalizeLatestTranscript(
  current: TranscriptEntry[],
  role?: TranscriptRole,
): TranscriptEntry[] {
  for (let index = current.length - 1; index >= 0; index -= 1) {
    const entry = current[index]
    if (entry.final) continue
    if (role && entry.role !== role) continue
    return current.map((item, itemIndex) =>
      itemIndex === index ? { ...item, final: true } : item,
    )
  }
  return current
}
