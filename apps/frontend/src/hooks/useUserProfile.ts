import { useState, useCallback } from 'react'
import type { UserProfile } from '@/types'

const STORAGE_KEY = 'visualizer-agent:user-profile'

function normalizeProfile(raw: Partial<UserProfile>): UserProfile {
  return {
    topics_visualized: raw.topics_visualized ?? [],
    unclear_topics: raw.unclear_topics ?? [],
    interaction_count: raw.interaction_count ?? 0,
  }
}

function saveProfile(profile: UserProfile): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile))
  } catch {
    // Ignore storage errors
  }
}

function getStoredProfile(): UserProfile | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return normalizeProfile(JSON.parse(stored) as Partial<UserProfile>)
    }
  } catch {
    // Ignore storage errors
  }
  return null
}

export function useUserProfile() {
  const [profile, setProfile] = useState<UserProfile>(() => {
    return getStoredProfile() || {
      topics_visualized: [],
      unclear_topics: [],
      interaction_count: 0,
    }
  })

  const trackTopic = useCallback((topic: string) => {
    setProfile((current) => {
      const updated = {
        ...current,
        topics_visualized: current.topics_visualized.includes(topic)
          ? current.topics_visualized
          : [...current.topics_visualized, topic],
      }
      saveProfile(updated)
      return updated
    })
  }, [])

  const trackUnclearTopic = useCallback((topic: string) => {
    setProfile((current) => {
      const updated = {
        ...current,
        unclear_topics: current.unclear_topics.includes(topic)
          ? current.unclear_topics
          : [...current.unclear_topics, topic],
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
    const empty: UserProfile = {
      topics_visualized: [],
      unclear_topics: [],
      interaction_count: 0,
    }
    setProfile(empty)
    saveProfile(empty)
  }, [])

  return {
    profile,
    trackTopic,
    trackUnclearTopic,
    incrementInteraction,
    resetProfile,
  }
}
