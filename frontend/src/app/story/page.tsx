'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function StoryRedirect() {
  const router = useRouter()
  useEffect(() => {
    router.replace('/guide')
  }, [router])
  return (
    <div className="loading-state">
      <div className="spinner" />
      Redirecting to How-to-Use guide…
    </div>
  )
}
