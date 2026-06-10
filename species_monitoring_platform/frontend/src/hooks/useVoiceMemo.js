import { useCallback, useEffect, useRef, useState } from 'react'

export default function useVoiceMemo({ maxDuration = 120000 } = {}) {
  const [recording, setRecording] = useState(false)
  const [duration, setDuration] = useState(0)
  const [memos, setMemos] = useState([])
  const [error, setError] = useState(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const timerRef = useRef(null)
  const startTimeRef = useRef(null)

  const start = useCallback(async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      const recorder = new MediaRecorder(stream, { mimeType })
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        clearInterval(timerRef.current)

        if (chunksRef.current.length > 0) {
          const blob = new Blob(chunksRef.current, { type: mimeType })
          const url = URL.createObjectURL(blob)
          const elapsed = Date.now() - (startTimeRef.current || Date.now())

          setMemos((prev) => [
            ...prev,
            {
              id: `memo-${Date.now()}`,
              blob,
              url,
              duration: Math.round(elapsed / 1000),
              timestamp: new Date().toISOString(),
              mimeType,
            },
          ])
        }

        setRecording(false)
        setDuration(0)
      }

      recorder.start(1000)
      recorderRef.current = recorder
      startTimeRef.current = Date.now()
      setRecording(true)

      timerRef.current = setInterval(() => {
        const elapsed = Date.now() - startTimeRef.current
        setDuration(Math.round(elapsed / 1000))
        if (elapsed >= maxDuration) {
          recorder.stop()
        }
      }, 500)
    } catch (err) {
      setError(err.message || 'Microphone access denied')
      setRecording(false)
    }
  }, [maxDuration])

  const stop = useCallback(() => {
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop()
    }
  }, [])

  const removeMemo = useCallback((id) => {
    setMemos((prev) => {
      const memo = prev.find((m) => m.id === id)
      if (memo?.url) URL.revokeObjectURL(memo.url)
      return prev.filter((m) => m.id !== id)
    })
  }, [])

  useEffect(() => () => {
    clearInterval(timerRef.current)
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop()
    }
    memos.forEach((m) => { if (m.url) URL.revokeObjectURL(m.url) })
  }, [])

  return { recording, duration, memos, error, start, stop, removeMemo }
}
