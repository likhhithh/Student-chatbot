import { useState, useEffect, useCallback } from 'react'
import { supabase } from '../lib/supabase'

const MAX_MEMORY = 20

export function useMemory(userId) {
  const [memories, setMemories] = useState([]) // [{id, topic, created_at}]

  // Load on mount
  useEffect(() => {
    if (!userId) return
    supabase
      .from('user_memory')
      .select('id, topic, created_at')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .limit(MAX_MEMORY)
      .then(({ data }) => { if (data) setMemories(data) })
  }, [userId])

  // Save a new topic after each user question
  const saveTopic = useCallback(async (topic) => {
    if (!userId || !topic?.trim()) return
    const clean = topic.trim().slice(0, 200)
    // Avoid duplicates within last 5 entries
    const recent = memories.slice(0, 5).map(m => m.topic.toLowerCase())
    if (recent.includes(clean.toLowerCase())) return

    const { data } = await supabase
      .from('user_memory')
      .insert({ user_id: userId, topic: clean })
      .select()
      .single()

    if (data) {
      setMemories(prev => {
        const next = [data, ...prev]
        return next.slice(0, MAX_MEMORY)
      })
    }
  }, [userId, memories])

  // Format recent topics as a string to inject into the prompt
  const buildContextString = useCallback((limit = 8) => {
    if (!memories.length) return ''
    return memories
      .slice(0, limit)
      .map(m => `- ${m.topic}`)
      .join('\n')
  }, [memories])

  return { memories, saveTopic, buildContextString }
}
