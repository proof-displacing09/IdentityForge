import { useCallback, useEffect, useRef, useState } from 'react'

/** IF-V5-06 (v6): explicit per-resource request states.
 *
 * States (never conflated):
 * - IDLE — never requested yet.
 * - LOADING — a request is in flight.
 * - READY — the last request succeeded; `data` is current.
 * - STALE — data exists from an earlier success, but a newer request
 *   failed (or is in flight after a failure); the old data is shown
 *   labelled STALE with its timestamp, never as fresh.
 * - ERROR — no data at all and the last request failed.
 * - NOT RUN — the resource was deliberately not requested (e.g. a tab
 *   never opened); distinct from ERROR.
 *
 * Correctness guarantees, all tested with deferred promises:
 * - A later success CLEARS a stale error (liveError is reset on
 *   success, not just on retry start).
 * - Responses are ignored after unmount (real useEffect cleanup) and
 *   after a newer request started (generation key) — including two
 *   overlapping retries completing out of order.
 * - Each request gets its own AbortController, aborted by the
 *   effect cleanup; the fetcher receives the signal. */

export type RequestState = 'IDLE' | 'LOADING' | 'READY' | 'STALE' | 'ERROR' | 'NOT RUN'

export interface ResourceResult<T> {
  state: RequestState
  data: T | null
  /** Last error message, or null. Cleared on success. */
  error: string | null
  /** When the current data was received (null when no data). */
  updatedAt: Date | null
  /** When the last failure happened (null when none / cleared). */
  errorAt: Date | null
  /** Re-run the fetch. Safe to call from a retry button. */
  retry: () => void
}

export function stateTone(state: RequestState): 'ok' | 'warn' | 'bad' | 'info' | 'neutral' | 'teal' {
  switch (state) {
    case 'READY': return 'teal'
    case 'STALE': return 'warn'
    case 'ERROR': return 'bad'
    case 'LOADING': return 'info'
    default: return 'neutral'
  }
}

export function stateLabel(state: RequestState): string {
  return state
}

/** Fetch a resource with explicit states. `fetcher` receives the
 *  AbortSignal for the current attempt; it should pass it to fetch
 *  (the api client accepts an optional signal). `enabled` false
 *  leaves the resource NOT RUN until retry() is called. */
export function useResource<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
  enabled = true,
): ResourceResult<T> {
  const [state, setState] = useState<RequestState>(enabled ? 'IDLE' : 'NOT RUN')
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [errorAt, setErrorAt] = useState<Date | null>(null)
  const generationRef = useRef(0)
  /** IF-V6-05: the CURRENT in-flight controller. Every run() aborts
   *  the previous controller before starting the next request, so a
   *  retry never leaves its predecessor running; unmount / disable
   *  aborts the latest controller (including retries) and invalidates
   *  the generation, suppressing late updates and cancelled errors. */
  const controllerRef = useRef<AbortController | null>(null)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const depsKey = JSON.stringify(deps)

  const run = useCallback(() => {
    const generation = ++generationRef.current
    // IF-V6-05: abort the previous in-flight request (initial load or
    // earlier retry) before starting this one. A superseded request
    // must not complete late and overwrite newer data.
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'LOADING'))
    // A retry does not clear a previous error until it succeeds —
    // but a stale error is shown as STALE data, not as a fresh ERROR.
    // The fetcher is invoked synchronously so the AbortSignal is
    // handed out (and the request started) inside this effect; a
    // synchronously-throwing fetcher becomes a rejection, not an
    // exception thrown out of the effect.
    let p: Promise<T>
    try {
      p = fetcherRef.current(controller.signal)
    } catch (e) {
      p = Promise.reject(e)
    }
    p.then(
      (value) => {
        if (generation !== generationRef.current) return // superseded
        setData(value)
        setError(null)
        setErrorAt(null)
        setUpdatedAt(new Date())
        setState('READY')
      },
      (e) => {
        if (generation !== generationRef.current) return // superseded
        // IF-V6-05: a rejection from an aborted (cancelled) request is
        // silent — it must not surface as an error over good data, and
        // must not turn a STALE-while-retrying view into an ERROR.
        if (controller.signal.aborted) return // unmounted / superseded / disabled
        setError(String(e))
        setErrorAt(new Date())
        setState((prev) => (prev === 'READY' || prev === 'STALE' || data !== null ? 'STALE' : 'ERROR'))
      },
    )
    return controller
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!enabled) {
      // IF-V6-05: disabling aborts any in-flight request (including a
      // retry) and invalidates its generation, so no late response can
      // present stale data as current. Nothing is left in flight.
      controllerRef.current?.abort()
      generationRef.current++
      setState('NOT RUN')
      return
    }
    const controller = run()
    // REAL cleanup, installed and returned: abort the in-flight
    // request and invalidate its generation so a late response is
    // ignored even if the fetch itself cannot be aborted.
    return () => {
      generationRef.current++
      controllerRef.current?.abort()
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, depsKey])

  // IF-V6-05: retry() is just run() — run() already bumps the
  // generation AND aborts the previous controller, so a retry can
  // never leave its predecessor running.
  const retry = useCallback(() => {
    run()
  }, [run])

  return { state, data, error, updatedAt, errorAt, retry }
}
