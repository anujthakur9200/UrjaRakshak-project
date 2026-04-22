'use client'

import { useEffect, useState } from 'react'

interface AnimatedNumberProps {
  value: number
  duration?: number
  decimals?: number
  suffix?: string
}

export function AnimatedNumber({ value, duration = 1000, decimals = 0, suffix = '' }: AnimatedNumberProps) {
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    let start = 0
    const step = value / (duration / 20)
    const interval = setInterval(() => {
      start += step
      if (start >= value) {
        setDisplay(value)
        clearInterval(interval)
      } else {
        setDisplay(start)
      }
    }, 20)

    return () => clearInterval(interval)
  }, [value, duration])

  return (
    <span className="animated-number">
      {display.toFixed(decimals)}{suffix}
    </span>
  )
}
