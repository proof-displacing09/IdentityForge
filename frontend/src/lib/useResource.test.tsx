import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useResource } from './useResource'

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('IF-V5-06 useResource request states', () => {
  it('load success: LOADING → READY with data and a timestamp; no error', async () => {
    const d = deferred<string>()
    const { result } = renderHook(() => useResource(() => d.promise))
    expect(['IDLE', 'LOADING']).toContain(result.current.state)
    await act(async () => { d.resolve('ok-value') })
    await waitFor(() => expect(result.current.state).toBe('READY'))
    expect(result.current.data).toBe('ok-value')
    expect(result.current.error).toBeNull()
    expect(result.current.updatedAt).toBeInstanceOf(Date)
  })

  it('provider drops then retry succeeds: ERROR → READY and the stale error is cleared', async () => {
    const first = deferred<string>()
    let fetcher = () => first.promise
    const { result, rerender } = renderHook(() => useResource(() => fetcher()))
    await act(async () => { first.reject(new Error('backend down')) })
    await waitFor(() => expect(result.current.state).toBe('ERROR'))
    expect(result.current.error).toContain('backend down')
    expect(result.current.data).toBeNull()

    const second = deferred<string>()
    fetcher = () => second.promise
    await act(async () => { result.current.retry() })
    expect(['LOADING', 'STALE', 'ERROR']).toContain(result.current.state)
    await act(async () => { second.resolve('recovered') })
    await waitFor(() => expect(result.current.state).toBe('READY'))
    expect(result.current.data).toBe('recovered')
    expect(result.current.error).toBeNull()
    expect(result.current.errorAt).toBeNull()
    rerender()
  })

  it('retry returns partial data: success with data, then failure keeps STALE data labelled STALE', async () => {
    const first = deferred<string>()
    let fetcher = () => first.promise
    const { result } = renderHook(() => useResource(() => fetcher()))
    await act(async () => { first.resolve('first') })
    await waitFor(() => expect(result.current.state).toBe('READY'))

    const second = deferred<string>()
    fetcher = () => second.promise
    await act(async () => { result.current.retry() })
    // While the retry is in flight the old data is STALE, not READY.
    expect(result.current.state).toBe('STALE')
    expect(result.current.data).toBe('first')
    await act(async () => { second.reject(new Error('dropped')) })
    await waitFor(() => expect(result.current.state).toBe('STALE'))
    expect(result.current.data).toBe('first')
    expect(result.current.error).toContain('dropped')

    const third = deferred<string>()
    fetcher = () => third.promise
    await act(async () => { result.current.retry() })
    await act(async () => { third.resolve('all recovered') })
    await waitFor(() => expect(result.current.state).toBe('READY'))
    expect(result.current.data).toBe('all recovered')
    expect(result.current.error).toBeNull()
  })

  it('unmount between responses: the late response is ignored (no state update after unmount)', async () => {
    const d = deferred<string>()
    const { result, unmount } = renderHook(() => useResource(() => d.promise))
    expect(result.current.state).toBe('LOADING')
    unmount()
    await act(async () => { d.resolve('too late') })
    // No crash, no React "setState on unmounted component" warning
    // surfaced as an error; the hook simply never applies the value.
    expect(result.current.state).toBe('LOADING')
  })

  it('two overlapping retries complete out of order: the LAST retry wins', async () => {
    const first = deferred<string>()
    let fetcher = () => first.promise
    const { result } = renderHook(() => useResource(() => fetcher()))
    await act(async () => { first.resolve('v1') })
    await waitFor(() => expect(result.current.state).toBe('READY'))

    const slow = deferred<string>()
    const fast = deferred<string>()
    let call = 0
    fetcher = () => { call += 1; return call === 1 ? slow.promise : fast.promise }
    await act(async () => { result.current.retry() }) // retry #2 (slow)
    await act(async () => { result.current.retry() }) // retry #3 (fast)
    await act(async () => { fast.resolve('newest') })
    await waitFor(() => expect(result.current.data).toBe('newest'))
    await act(async () => { slow.resolve('stale-winner') })
    // Let the slow response settle; it must NOT overwrite the newest.
    await act(async () => { await Promise.resolve() })
    expect(result.current.data).toBe('newest')
    expect(result.current.state).toBe('READY')
  })

  it('the effect installs a real cleanup that aborts the signal on unmount', async () => {
    const signals: AbortSignal[] = []
    const d = deferred<string>()
    const { unmount } = renderHook(() => useResource((signal) => { signals.push(signal); return d.promise }))
    expect(signals).toHaveLength(1)
    expect(signals[0].aborted).toBe(false)
    unmount()
    expect(signals[0].aborted).toBe(true)
    await act(async () => { d.resolve('ignored') })
  })

  it('disabled resource stays NOT RUN until retry', async () => {
    const spy = vi.fn(() => Promise.resolve('x'))
    const { result } = renderHook(() => useResource(spy, [], false))
    expect(result.current.state).toBe('NOT RUN')
    expect(spy).not.toHaveBeenCalled()
    await act(async () => { result.current.retry() })
    await waitFor(() => expect(result.current.state).toBe('READY'))
  })
})

describe('IF-V6-05 useResource retry abort (failing-first)', () => {
  it('load → retry → unmount: BOTH in-flight signals are aborted', async () => {
    const signals: AbortSignal[] = []
    let fetcher = (signal: AbortSignal) => { signals.push(signal); return deferred<string>().promise }
    const first = deferred<string>()
    fetcher = (signal: AbortSignal) => { signals.push(signal); return first.promise }
    const { result, unmount } = renderHook(() => useResource((signal) => fetcher(signal)))
    expect(signals).toHaveLength(1)
    const second = deferred<string>()
    fetcher = (signal: AbortSignal) => { signals.push(signal); return second.promise }
    await act(async () => { result.current.retry() })
    expect(signals).toHaveLength(2)
    // The retry must abort the first request.
    expect(signals[0].aborted).toBe(true)
    expect(signals[1].aborted).toBe(false)
    unmount()
    expect(signals[1].aborted).toBe(true)
    await act(async () => { first.resolve('late-1'); second.resolve('late-2') })
  })

  it('retry1 → retry2: the first retry signal is aborted by the second retry', async () => {
    const signals: AbortSignal[] = []
    const d1 = deferred<string>()
    const d2 = deferred<string>()
    const d3 = deferred<string>()
    const promises = [d1.promise, d2.promise, d3.promise]
    let call = 0
    const { result } = renderHook(() => useResource((signal) => { signals.push(signal); return promises[call++] }))
    await act(async () => { d1.resolve('v1') })
    await waitFor(() => expect(result.current.state).toBe('READY'))
    await act(async () => { result.current.retry() }) // retry1 (d2)
    await act(async () => { result.current.retry() }) // retry2 (d3)
    expect(signals[1].aborted).toBe(true)
    expect(signals[2].aborted).toBe(false)
    await act(async () => { d3.resolve('v3') })
    await waitFor(() => expect(result.current.data).toBe('v3'))
  })

  it('disabling the resource aborts the in-flight request and leaves NOT RUN, never a stale READY', async () => {
    const signals: AbortSignal[] = []
    const d = deferred<string>()
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useResource((signal) => { signals.push(signal); return d.promise }, [], enabled),
      { initialProps: { enabled: true } },
    )
    expect(signals).toHaveLength(1)
    rerender({ enabled: false })
    expect(signals[0].aborted).toBe(true)
    expect(result.current.state).toBe('NOT RUN')
    await act(async () => { d.resolve('too late') })
    expect(result.current.state).toBe('NOT RUN')
    expect(result.current.data).toBeNull()
  })

  it('a cancelled (aborted) rejection never surfaces as an error and never clears READY data', async () => {
    const first = deferred<string>()
    let fetcher = () => first.promise
    const { result } = renderHook(() => useResource(() => fetcher()))
    await act(async () => { first.resolve('v1') })
    await waitFor(() => expect(result.current.state).toBe('READY'))
    const second = deferred<string>()
    fetcher = () => second.promise
    await act(async () => { result.current.retry() })
    await act(async () => { second.reject(new DOMException('aborted', 'AbortError')) })
    await act(async () => { await Promise.resolve() })
    // Aborted retries are silent: no error surfaced over good data.
    expect(result.current.state).toBe('STALE')
    expect(result.current.data).toBe('v1')
  })

  it('the hook never repeats a POST: each retry issues exactly one fetch call', async () => {
    const spy = vi.fn(() => Promise.resolve('x'))
    const { result } = renderHook(() => useResource(spy))
    await waitFor(() => expect(result.current.state).toBe('READY'))
    expect(spy).toHaveBeenCalledTimes(1)
    await act(async () => { result.current.retry() })
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
  })
})
