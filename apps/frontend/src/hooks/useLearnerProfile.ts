import { useState, useCallback } from 'react'
import type { LearnerProfile } from '@/types'

const STORAGE_KEY = 'visualizer-agent:learner-profile'

function getStoredProfile(): LearnerProfile | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored) as LearnerProfile
    }
  } catch {
    // Ignore storage errors
  }
  return null
}

function saveProfile(profile: LearnerProfile): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile))
  } catch {
    // Ignore storage errors
  }
}

export function useLearnerProfile() {
  const [profile, setProfile] = useState<LearnerProfile>(() => {
    return getStoredProfile() || {
      concepts_seen: [],
      struggling_with: [],
      interaction_count: 0,
    }
  })

  const trackConcept = useCallback((concept: string) => {
    setProfile((current) => {
      const updated = {
        ...current,
        concepts_seen: current.concepts_seen.includes(concept)
          ? current.concepts_seen
          : [...current.concepts_seen, concept],
      }
      saveProfile(updated)
      return updated
    })
  }, [])

  const trackStruggle = useCallback((concept: string) => {
    setProfile((current) => {
      const updated = {
        ...current,
        struggling_with: current.struggling_with.includes(concept)
          ? current.struggling_with
          : [...current.struggling_with, concept],
      }
      saveProfile(updated)
      return updated
    })
  }, [])

  const incrementInteraction = useCallback(() => {
    setProfile((current) => {
      const updated = {
        ...current,
        interaction_count: current.interaction_count + 1,
      }
      saveProfile(updated)
      return updated
    })
  }, [])

  const resetProfile = useCallback(() => {
    const empty: LearnerProfile = {
      concepts_seen: [],
      struggling_with: [],
      interaction_count: 0,
    }
    setProfile(empty)
    saveProfile(empty)
  }, [])

  return {
    profile,
    trackConcept,
    trackStruggle,
    incrementInteraction,
    resetProfile,
  }
}