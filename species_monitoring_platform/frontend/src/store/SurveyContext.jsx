import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import {
  loadSurveyState,
  saveSurveyState,
} from '../lib/surveyOffline'
import {
  isNativeMobile,
  loadNativeSurveyState,
  saveNativeSurveyState,
} from '../lib/mobileNative'
import { mergeStoredSurveyState } from '../lib/surveyOffline'

/**
 * Central survey state context.
 *
 * Replaces the FieldOpsTab-local `useState(() => loadSurveyState())`
 * with a shared context so child components can access / mutate
 * survey state without prop-drilling.
 *
 * The setter follows the same functional-update pattern as React's
 * setState, so existing call sites like
 *   `setSurveyState(current => ({ ...current, activeRouteId: '' }))`
 * work without any changes.
 */

const SurveyStateContext = createContext(null)
const SurveyDispatchContext = createContext(null)

export function SurveyProvider({ children }) {
  const [surveyState, setSurveyState] = useState(() => loadSurveyState())
  const nativeMobile = isNativeMobile()
  const [nativeHydrationComplete, setNativeHydrationComplete] = useState(() => !nativeMobile)

  // --- persistence: debounced write to localStorage + native storage ---
  useEffect(() => {
    const timer = setTimeout(() => {
      saveSurveyState(surveyState)
      if (!nativeMobile || nativeHydrationComplete) {
        saveNativeSurveyState(surveyState).catch(() => {})
      }
    }, 1000)
    return () => clearTimeout(timer)
  }, [nativeHydrationComplete, nativeMobile, surveyState])

  // --- native hydration: merge Capacitor-stored state on first mount ---
  useEffect(() => {
    if (!nativeMobile) {
      setNativeHydrationComplete(true)
      return undefined
    }
    let cancelled = false

    loadNativeSurveyState()
      .then((nativeState) => {
        if (!nativeState || cancelled) return
        setSurveyState((current) => mergeStoredSurveyState(current, nativeState))
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setNativeHydrationComplete(true)
      })

    return () => {
      cancelled = true
    }
  }, [nativeMobile])

  return (
    <SurveyStateContext.Provider value={surveyState}>
      <SurveyDispatchContext.Provider value={setSurveyState}>
        {children}
      </SurveyDispatchContext.Provider>
    </SurveyStateContext.Provider>
  )
}

/**
 * Read survey state.
 * @returns {import('../lib/surveyOffline').SurveyState}
 */
export function useSurveyState() {
  const ctx = useContext(SurveyStateContext)
  if (ctx === null) throw new Error('useSurveyState must be used inside <SurveyProvider>')
  return ctx
}

/**
 * Get the survey state setter (same API as React setState).
 * Accepts either a new state object or a functional updater.
 */
export function useSurveyDispatch() {
  const ctx = useContext(SurveyDispatchContext)
  if (ctx === null) throw new Error('useSurveyDispatch must be used inside <SurveyProvider>')
  return ctx
}

/**
 * Convenience hook: returns [surveyState, setSurveyState].
 * Drop-in replacement for the old `useState(() => loadSurveyState())`.
 */
export function useSurveyStore() {
  return [useSurveyState(), useSurveyDispatch()]
}
