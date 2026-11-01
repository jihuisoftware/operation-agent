// Dedicated-worker timers keep queue polling alive when the host window is hidden.
globalThis.onmessage = ({ data }: MessageEvent) => {
  if (data.kind === 'start') {
    setInterval(() => globalThis.postMessage({ kind: 'tick' }), data.ms)
  } else if (data.kind === 'sleep') {
    setTimeout(() => globalThis.postMessage({ kind: 'wake', id: data.id }), data.ms)
  }
}

export {}
