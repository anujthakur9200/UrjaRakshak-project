'use client'

import { useEffect } from 'react'

/**
 * Runs once on the client and stamps data-platform + data-touch on <body>.
 * CSS can then use body[data-platform="ios"] { ... } selectors.
 */
export function PlatformDetect() {
  useEffect(() => {
    const ua = navigator.userAgent
    const platform = navigator.platform ?? ''

    let os: string
    if (/iPad|iPhone|iPod/.test(ua) || (/Mac/.test(platform) && navigator.maxTouchPoints > 1)) {
      os = 'ios'
    } else if (/Android/.test(ua)) {
      os = 'android'
    } else if (/Mac/.test(ua)) {
      os = 'macos'
    } else if (/Win/.test(ua)) {
      os = 'windows'
    } else if (/Linux/.test(ua)) {
      os = 'linux'
    } else {
      os = 'other'
    }

    document.body.dataset.platform = os

    // Touch device check
    const isTouch = navigator.maxTouchPoints > 0 || 'ontouchstart' in window
    document.body.dataset.touch = isTouch ? 'true' : 'false'
  }, [])

  return null
}
