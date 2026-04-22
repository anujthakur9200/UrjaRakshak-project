/**
 * UrjaRakshak logo — a shield with a lightning bolt inside.
 * "Urja" = Energy, "Rakshak" = Guardian/Protector
 */
export function UrjaRakshakLogo({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 36 36"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="UrjaRakshak logo"
    >
      {/* Shield shape */}
      <path
        d="M18 3 L32 8.5 L32 19.5 C32 26.5 26 31.5 18 34 C10 31.5 4 26.5 4 19.5 L4 8.5 Z"
        fill="url(#logo-shield-fill)"
        stroke="url(#logo-shield-stroke)"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      {/* Lightning bolt */}
      <path
        d="M20.5 9 L13 20 L18 20 L15.5 27 L23 16 L18 16 Z"
        fill="url(#logo-bolt-fill)"
        filter="url(#logo-glow)"
      />
      <defs>
        <linearGradient id="logo-shield-fill" x1="4" y1="3" x2="32" y2="34" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0AF0FF" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#4D94FF" stopOpacity="0.12" />
        </linearGradient>
        <linearGradient id="logo-shield-stroke" x1="4" y1="3" x2="32" y2="34" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0AF0FF" stopOpacity="0.90" />
          <stop offset="100%" stopColor="#9B72FF" stopOpacity="0.70" />
        </linearGradient>
        <linearGradient id="logo-bolt-fill" x1="13" y1="9" x2="23" y2="27" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.95" />
          <stop offset="60%" stopColor="#0AF0FF" />
          <stop offset="100%" stopColor="#4D94FF" />
        </linearGradient>
        <filter id="logo-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
    </svg>
  )
}
