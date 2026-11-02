import { beforeEach, vi } from 'vitest'

// jsdom has no layout observer; browser layout is verified separately.
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
})
