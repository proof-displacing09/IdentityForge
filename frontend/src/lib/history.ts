import type { RunResult } from '../types'

const KEY = 'identityforge.runs.v1'

export function loadRuns(): RunResult[] {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as RunResult[]) : []
  } catch {
    return []
  }
}

export function saveRuns(runs: RunResult[]): void {
  try { localStorage.setItem(KEY, JSON.stringify(runs.slice(0, 100))) } catch { /* storage full/unavailable: history is best-effort */ }
}

export function clearRuns(): void {
  try { localStorage.removeItem(KEY) } catch { /* ignore */ }
}
