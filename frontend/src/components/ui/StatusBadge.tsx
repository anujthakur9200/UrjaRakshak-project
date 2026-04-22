'use client'

type StatusValue =
  | 'healthy'
  | 'warning'
  | 'critical'
  | 'offline'
  | 'balanced'
  | 'minor_imbalance'
  | 'significant_imbalance'
  | 'critical_imbalance'
  | 'uncertain'

interface StatusBadgeProps {
  status: StatusValue
}

const STATUS_MAP: Record<StatusValue, { label: string; chipClass: string }> = {
  healthy:                { label: 'Healthy',               chipClass: 'chip chip-ok' },
  warning:                { label: 'Warning',               chipClass: 'chip chip-warn' },
  critical:               { label: 'Critical',              chipClass: 'chip chip-err' },
  offline:                { label: 'Offline',               chipClass: 'chip chip-err' },
  balanced:               { label: 'Balanced',              chipClass: 'chip chip-ok' },
  minor_imbalance:        { label: 'Minor Imbalance',       chipClass: 'chip chip-warn' },
  significant_imbalance:  { label: 'Significant Imbalance', chipClass: 'chip chip-err' },
  critical_imbalance:     { label: 'Critical Imbalance',    chipClass: 'chip chip-err' },
  uncertain:              { label: 'Uncertain',             chipClass: 'chip chip-cyan' },
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const { label, chipClass } = STATUS_MAP[status] ?? {
    label: status,
    chipClass: 'chip',
  }
  return <span className={chipClass}>{label}</span>
}
