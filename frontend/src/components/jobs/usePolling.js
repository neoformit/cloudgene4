import { onBeforeUnmount } from 'vue'

/**
 * Poll `fn` while `shouldContinue()` is true. Starts at `interval` ms; when `fn` reports no
 * change (returns false) or fails, the delay grows ×1.5 up to `maxInterval`; any change resets it
 * (SPEC §3.1: 2 s while active, backoff to 10 s). Stops automatically on unmount.
 */
export function createPoller(fn, { interval = 2000, maxInterval = 10000, shouldContinue = () => true } = {}) {
  let timer = null
  let delay = interval
  let stopped = true

  async function tick() {
    timer = null
    if (stopped) return
    let changed = true
    try {
      changed = (await fn()) !== false
    } catch {
      changed = false
    }
    if (stopped || !shouldContinue()) {
      stopped = true
      return
    }
    delay = changed ? interval : Math.min(Math.round(delay * 1.5), maxInterval)
    timer = setTimeout(tick, delay)
  }

  return {
    start() {
      if (!stopped) return
      stopped = false
      delay = interval
      timer = setTimeout(tick, delay)
    },
    stop() {
      stopped = true
      if (timer) clearTimeout(timer)
      timer = null
    },
    get running() {
      return !stopped
    },
    get delay() {
      return delay
    },
  }
}

export function usePolling(fn, options) {
  const poller = createPoller(fn, options)
  onBeforeUnmount(() => poller.stop())
  return poller
}
