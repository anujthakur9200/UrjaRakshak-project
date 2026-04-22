'use client'

import { useEffect, useState } from 'react'

export type Platform = 'mac' | 'windows' | 'ios' | 'android' | 'linux' | 'unknown'
export type DeviceType = 'mobile' | 'tablet' | 'desktop'

export function usePlatform() {
  const [platform, setPlatform] = useState<Platform>('unknown')
  const [deviceType, setDeviceType] = useState<DeviceType>('desktop')
  const [isTouchDevice, setIsTouchDevice] = useState(false)

  useEffect(() => {
    const ua = navigator.userAgent.toLowerCase()
    const isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0
    setIsTouchDevice(isTouch)

    // Platform detection
    if (ua.includes('iphone')) {
      setPlatform('ios')
      setDeviceType('mobile')
      document.body.dataset.platform = 'ios'
      document.body.dataset.device = 'mobile'
    } else if (ua.includes('ipad') || (ua.includes('macintosh') && isTouch)) {
      setPlatform('ios')
      setDeviceType('tablet')
      document.body.dataset.platform = 'ios'
      document.body.dataset.device = 'tablet'
    } else if (ua.includes('android')) {
      setPlatform('android')
      setDeviceType(ua.includes('mobile') ? 'mobile' : 'tablet')
      document.body.dataset.platform = 'android'
      document.body.dataset.device = ua.includes('mobile') ? 'mobile' : 'tablet'
    } else if (ua.includes('mac')) {
      setPlatform('mac')
      setDeviceType('desktop')
      document.body.dataset.platform = 'mac'
    } else if (ua.includes('win')) {
      setPlatform('windows')
      setDeviceType('desktop')
      document.body.dataset.platform = 'windows'
    } else if (ua.includes('linux')) {
      setPlatform('linux')
      setDeviceType('desktop')
      document.body.dataset.platform = 'linux'
    }
  }, [])

  return { platform, deviceType, isTouchDevice }
}
