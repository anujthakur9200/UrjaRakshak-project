'use client'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'
import { StatusBadge } from '@/components/ui/StatusBadge'

interface AnalysisRecord {
  id: string
  substation_id: string
  residual_pct: number
  confidence: number
  balance_status: string
  created_at: string
  [key: string]: unknown
}

const PAGE_SIZE = 15

export default function HistoryPage() {
  const [records, setRecords] = useState<AnalysisRecord[]>([])
  const [filtered, setFiltered] = useState<AnalysisRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchSub, setSearchSub] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<AnalysisRecord | null>(null)
  const [total, setTotal] = useState(0)

  const load = useCallback(async (offset: number) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.listAnalyses({ limit: PAGE_SIZE, offset })
      const items: AnalysisRecord[] = Array.isArray(res)
        ? res
        : Array.isArray(res?.items)
        ? res.items
        : Array.isArray(res?.results)
        ? res.results
        : []
      const count: number = res?.total ?? res?.count ?? items.length
      setRecords(items)
      setTotal(count)
    } catch (err: any) {
      setError(err?.message || 'Failed to load analyses')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(page * PAGE_SIZE)
  }, [page, load])

  // Client-side filtering
  useEffect(() => {
    let result = records
    if (searchSub.trim()) {
      const q = searchSub.toLowerCase()
      result = result.filter((r) => r.substation_id?.toLowerCase().includes(q))
    }
    if (filterStatus) {
      result = result.filter((r) => r.balance_status === filterStatus)
    }
    setFiltered(result)
  }, [records, searchSub, filterStatus])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function formatDate(s: string) {
    try {
      return new Date(s).toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return s
    }
  }

  function confidenceColor(c: number): string {
    if (c >= 0.85) return 'var(--green)'
    if (c >= 0.65) return 'var(--blue)'
    if (c >= 0.45) return 'var(--amber)'
    return 'var(--red)'
  }

  function lossColor(pct: number): string {
    if (pct <= 2) return 'var(--green)'
    if (pct <= 5) return 'var(--amber)'
    return 'var(--red)'
  }

  const statusOptions = [
    '',
    'balanced',
    'minor_imbalance',
    'significant_imbalance',
    'critical_imbalance',
    'uncertain',
  ]

  return (
    <main className="page">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Analysis History</h1>
          <p className="page-desc">
            Browse past physics-based loss analyses. Filter by substation or balance status and
            click any row for full details.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div
        className="panel-elevated"
        style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 20, padding: '12px 16px' }}
      >
        <input
          className="input"
          placeholder="Search substation ID…"
          value={searchSub}
          onChange={(e) => { setSearchSub(e.target.value); setPage(0) }}
          style={{ width: 220, fontFamily: 'var(--font-mono)', fontSize: 13 }}
        />
        <select
          className="input"
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value); setPage(0) }}
          style={{ fontFamily: 'var(--font-mono)', fontSize: 13, minWidth: 200 }}
        >
          <option value="">All statuses</option>
          {statusOptions.filter(Boolean).map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
          {filtered.length} of {total} records
        </span>
      </div>

      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
        {/* Table */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {error && (
            <div className="panel" style={{ borderColor: 'var(--red)', color: 'var(--red)', padding: 16, marginBottom: 16, fontFamily: 'var(--font-mono)', fontSize: 13 }}>
              {error}
            </div>
          )}

          <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="data-table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Date / Time</th>
                  <th>Substation</th>
                  <th>Loss %</th>
                  <th>Confidence</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: 32, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                      Loading analyses…
                    </td>
                  </tr>
                )}
                {!loading && filtered.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: 32, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 13 }}>
                      No records found
                    </td>
                  </tr>
                )}
                {!loading && filtered.map((rec) => (
                  <tr
                    key={rec.id}
                    onClick={() => setSelected(selected?.id === rec.id ? null : rec)}
                    style={{
                      cursor: 'pointer',
                      background: selected?.id === rec.id ? 'rgba(0,212,255,0.06)' : undefined,
                      transition: 'background 0.15s',
                    }}
                  >
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
                      {formatDate(rec.created_at)}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--cyan)' }}>
                      {rec.substation_id}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: lossColor(rec.residual_pct), fontWeight: 600 }}>
                      {Number(rec.residual_pct).toFixed(2)}%
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: confidenceColor(rec.confidence) }}>
                      {(rec.confidence * 100).toFixed(1)}%
                    </td>
                    <td>
                      <StatusBadge status={rec.balance_status as any} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, marginTop: 16 }}>
            <button
              className="btn btn-secondary"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0 || loading}
            >
              ← Prev
            </button>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
              Page {page + 1} / {totalPages}
            </span>
            <button
              className="btn btn-secondary"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1 || loading}
            >
              Next →
            </button>
          </div>
        </div>

        {/* Side detail panel */}
        {selected && (
          <div
            className="panel-elevated"
            style={{ width: 280, flexShrink: 0, position: 'sticky', top: 80 }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <span style={{ fontFamily: 'var(--font-ui)', fontWeight: 600, color: 'var(--text-primary)', fontSize: 15 }}>
                Analysis Detail
              </span>
              <button
                className="btn btn-secondary"
                onClick={() => setSelected(null)}
                style={{ padding: '2px 8px', fontSize: 13 }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { label: 'ID',          value: selected.id },
                { label: 'Substation',  value: selected.substation_id },
                { label: 'Date',        value: formatDate(selected.created_at) },
                { label: 'Loss %',      value: `${Number(selected.residual_pct).toFixed(3)}%`,   color: lossColor(selected.residual_pct) },
                { label: 'Confidence',  value: `${(selected.confidence * 100).toFixed(1)}%`,     color: confidenceColor(selected.confidence) },
              ].map(({ label, value, color }) => (
                <div key={label}>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 3 }}>
                    {label}
                  </p>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: color ?? 'var(--text-primary)', margin: 0, wordBreak: 'break-all' }}>
                    {String(value)}
                  </p>
                </div>
              ))}
              <div>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>
                  Balance Status
                </p>
                <StatusBadge status={selected.balance_status as any} />
              </div>

              {/* Additional raw fields */}
              {Object.entries(selected)
                .filter(([k]) => !['id','substation_id','created_at','residual_pct','confidence','balance_status'].includes(k))
                .slice(0, 6)
                .map(([k, v]) => (
                  <div key={k}>
                    <p style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 3 }}>
                      {k.replace(/_/g, ' ')}
                    </p>
                    <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)', margin: 0, wordBreak: 'break-all' }}>
                      {typeof v === 'object' ? JSON.stringify(v) : String(v ?? '—')}
                    </p>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
