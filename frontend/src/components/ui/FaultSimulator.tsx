'use client'

import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface FaultType {
  id: string
  label: string
  description: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  duration: number   // seconds
  icon: string
  effects: string[]
}

const FAULT_TYPES: FaultType[] = [
  {
    id: 'line-fault',
    label: 'Line-to-Ground Fault',
    description: 'Single phase contacts ground, causing overcurrent and voltage sag.',
    severity: 'high',
    duration: 8,
    icon: '⚡',
    effects: ['Voltage drop 15%', 'Overcurrent 3×', 'Protection relay trip'],
  },
  {
    id: 'transformer-fault',
    label: 'Transformer Overload',
    description: 'Transformer exceeds rated capacity, thermal stress and insulation degradation.',
    severity: 'medium',
    duration: 12,
    icon: '🔥',
    effects: ['Temperature +40°C', 'Efficiency loss 8%', 'Alarm triggered'],
  },
  {
    id: 'frequency-dip',
    label: 'Frequency Excursion',
    description: 'Sudden load increase causes frequency to deviate from 50 Hz nominal.',
    severity: 'critical',
    duration: 6,
    icon: '📉',
    effects: ['Freq 49.2 Hz', 'Load shedding activated', 'UFLS relay trip'],
  },
  {
    id: 'voltage-sag',
    label: 'Voltage Sag Event',
    description: 'Short-duration rms voltage drop due to remote fault or motor starting.',
    severity: 'low',
    duration: 4,
    icon: '📊',
    effects: ['Voltage 85% nominal', 'Sensitive loads affected', 'DVIR recorded'],
  },
  {
    id: 'islanding',
    label: 'Islanding Detected',
    description: 'Grid section becomes isolated, operating without main grid connection.',
    severity: 'critical',
    duration: 10,
    icon: '🏝️',
    effects: ['Grid disconnect', 'Frequency drift', 'Anti-islanding protection'],
  },
]

const SEVERITY_COLORS = {
  low:      { bg: 'rgba(0,212,255,0.1)',   border: '#00D4FF', text: '#00D4FF' },
  medium:   { bg: 'rgba(255,176,32,0.1)',  border: '#FFB020', text: '#FFB020' },
  high:     { bg: 'rgba(255,107,53,0.1)',  border: '#FF6B35', text: '#FF6B35' },
  critical: { bg: 'rgba(255,68,85,0.1)',   border: '#FF4455', text: '#FF4455' },
}

interface FaultEvent {
  id: number
  fault: FaultType
  startedAt: Date
  progress: number  // 0-100
  resolved: boolean
}

export function FaultSimulator() {
  const [events, setEvents] = useState<FaultEvent[]>([])
  const [isSimulating, setIsSimulating] = useState(false)
  const [selectedFault, setSelectedFault] = useState<FaultType>(FAULT_TYPES[0])
  const nextId = useRef(1)
  const intervalsRef = useRef<Map<number, NodeJS.Timeout>>(new Map())

  function triggerFault(fault: FaultType) {
    const id = nextId.current++
    const event: FaultEvent = {
      id,
      fault,
      startedAt: new Date(),
      progress: 0,
      resolved: false,
    }
    setEvents(prev => [event, ...prev].slice(0, 6))

    // Animate progress
    const totalMs  = fault.duration * 1000
    const interval = 100
    let elapsed    = 0
    const timer    = setInterval(() => {
      elapsed += interval
      const progress = Math.min(100, (elapsed / totalMs) * 100)
      setEvents(prev => prev.map(e => e.id === id ? { ...e, progress } : e))
      if (elapsed >= totalMs) {
        clearInterval(timer)
        intervalsRef.current.delete(id)
        setEvents(prev => prev.map(e => e.id === id ? { ...e, resolved: true, progress: 100 } : e))
      }
    }, interval)
    intervalsRef.current.set(id, timer)
  }

  function runAutoSim() {
    if (isSimulating) {
      setIsSimulating(false)
      return
    }
    setIsSimulating(true)
    let i = 0
    const faults = [...FAULT_TYPES].sort(() => Math.random() - 0.5)
    const run = () => {
      if (i < faults.length) {
        triggerFault(faults[i++])
        setTimeout(run, 3500)
      } else {
        setIsSimulating(false)
      }
    }
    run()
  }

  // Cleanup
  useEffect(() => {
    const refs = intervalsRef.current
    return () => refs.forEach(t => clearInterval(t))
  }, [])

  const activeCount   = events.filter(e => !e.resolved).length
  const resolvedCount = events.filter(e =>  e.resolved).length

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>
            Fault Simulator
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {activeCount > 0 && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--red)',
                display: 'flex', alignItems: 'center', gap: 5,
              }}>
                <span className="status-dot status-dot-red status-dot-pulse" />
                {activeCount} active fault{activeCount > 1 ? 's' : ''}
              </span>
            )}
            {resolvedCount > 0 && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--green)' }}>
                ✓ {resolvedCount} resolved
              </span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={runAutoSim}
            style={{ borderColor: isSimulating ? 'var(--amber)' : undefined, color: isSimulating ? 'var(--amber)' : undefined }}
          >
            {isSimulating ? '⏸ Stop Auto' : '▶ Auto Sim'}
          </button>
          <button
            className="btn btn-danger btn-sm"
            onClick={() => triggerFault(selectedFault)}
          >
            ⚡ Trigger Fault
          </button>
        </div>
      </div>

      {/* Fault type selector */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
        {FAULT_TYPES.map(fault => {
          const clr = SEVERITY_COLORS[fault.severity]
          const sel = selectedFault.id === fault.id
          return (
            <button
              key={fault.id}
              onClick={() => setSelectedFault(fault)}
              style={{
                background: sel ? clr.bg : 'var(--bg-panel)',
                border: `1px solid ${sel ? clr.border : 'var(--border-subtle)'}`,
                borderRadius: 8,
                padding: '10px 12px',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.15s ease',
                boxShadow: sel ? `0 0 12px ${clr.border}33` : 'none',
              }}
            >
              <div style={{ fontSize: 16, marginBottom: 4 }}>{fault.icon}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: sel ? clr.text : 'var(--text-secondary)', fontWeight: 600, lineHeight: 1.3 }}>
                {fault.label}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: clr.text, textTransform: 'uppercase', marginTop: 3 }}>
                {fault.severity}
              </div>
            </button>
          )
        })}
      </div>

      {/* Selected fault details */}
      <motion.div
        key={selectedFault.id}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass"
        style={{ padding: '12px 16px' }}
      >
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
          {selectedFault.description}
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {selectedFault.effects.map(eff => (
            <span key={eff} style={{
              fontFamily: 'var(--font-mono)', fontSize: 9, padding: '2px 8px',
              borderRadius: 4, background: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)', color: 'var(--text-tertiary)',
            }}>
              {eff}
            </span>
          ))}
        </div>
      </motion.div>

      {/* Event log */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>
          Event Log
        </div>
        {events.length === 0 && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-dim)', textAlign: 'center', padding: '20px 0' }}>
            No fault events. Trigger a simulation above.
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <AnimatePresence>
            {events.map(ev => {
              const clr = SEVERITY_COLORS[ev.fault.severity]
              return (
                <motion.div
                  key={ev.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  style={{
                    background: ev.resolved ? 'transparent' : clr.bg,
                    border: `1px solid ${ev.resolved ? 'var(--border-ghost)' : clr.border}`,
                    borderRadius: 8,
                    padding: '10px 12px',
                    transition: 'background 0.5s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: ev.resolved ? 0 : 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{ev.fault.icon}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: ev.resolved ? 'var(--text-tertiary)' : clr.text }}>
                        {ev.fault.label}
                      </span>
                      {!ev.resolved && (
                        <span className="status-dot status-dot-red status-dot-pulse" />
                      )}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {ev.resolved ? (
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--green)' }}>✓ RESOLVED</span>
                      ) : (
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: clr.text, textTransform: 'uppercase' }}>
                          {ev.fault.severity}
                        </span>
                      )}
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8.5, color: 'var(--text-dim)' }}>
                        {ev.startedAt.toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                  {!ev.resolved && (
                    <div style={{ height: 3, background: 'var(--border-subtle)', borderRadius: 2, overflow: 'hidden' }}>
                      <motion.div
                        style={{ height: '100%', background: clr.border, borderRadius: 2 }}
                        initial={{ width: 0 }}
                        animate={{ width: `${ev.progress}%` }}
                        transition={{ duration: 0.1 }}
                      />
                    </div>
                  )}
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
