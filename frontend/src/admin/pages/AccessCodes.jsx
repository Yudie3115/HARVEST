import { useCallback, useEffect, useState } from 'react'
import { Check, ChevronDown, ChevronUp, Copy, KeyRound, Pencil, RotateCcw, ShieldOff } from 'lucide-react'
import { adminApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Input, Textarea } from '../../components/ui/input'
import { Alert, AlertDescription } from '../../components/ui/alert'

const PAGE_SIZE = 20
const TABS = [
  { value: '', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'revoked', label: 'Revoked' },
]

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '—'
}

function CreateForm({ onCreated }) {
  const [label, setLabel] = useState('')
  const [monthlyLimit, setMonthlyLimit] = useState('100')
  const [organizationName, setOrganizationName] = useState('')
  const [contactMessage, setContactMessage] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [created, setCreated] = useState(null)
  const [copied, setCopied] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (!label.trim() || monthlyLimit === '') return
    setCreating(true)
    setError(null)
    try {
      const result = await adminApi.createAccessCode({
        label: label.trim(),
        monthly_limit: Number(monthlyLimit),
        organization_name: organizationName.trim() || null,
        contact_message: contactMessage.trim() || null,
      })
      setCreated(result)
      setLabel('')
      setMonthlyLimit('100')
      setOrganizationName('')
      setContactMessage('')
      onCreated(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setCreating(false)
    }
  }

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(created.code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard access denied — the code remains visible to copy manually.
    }
  }

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle>Issue an access code</CardTitle>
        <p className="text-[11px] text-admin-muted">
          Creates a three-word code an admin shares with a group. It is shown once, in full, here.
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        {created && (
          <Alert variant="success" className="mb-4">
            <AlertDescription>
              <p className="mb-2 text-[12px]">
                Code for <b>{created.label}</b> — save it now, it will not be shown again.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded border border-green-500/20 bg-black/30 px-3 py-2 font-mono text-sm text-green-100">
                  {created.code}
                </code>
                <Button type="button" size="sm" variant="outline" onClick={copyCode}>
                  {copied ? <Check size={12} /> : <Copy size={12} />}
                  {copied ? 'Copied' : 'Copy'}
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        )}

        <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-[11px] text-admin-muted">Label *</label>
            <Input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="e.g. Kabale extension office"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-admin-muted">Monthly message limit *</label>
            <Input
              type="number"
              min="0"
              value={monthlyLimit}
              onChange={(event) => setMonthlyLimit(event.target.value)}
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-admin-muted">Organization (optional)</label>
            <Input
              value={organizationName}
              onChange={(event) => setOrganizationName(event.target.value)}
              placeholder="Shown to the group using the code"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-admin-muted">Replacement-code contact info (optional)</label>
            <Input
              value={contactMessage}
              onChange={(event) => setContactMessage(event.target.value)}
              placeholder="Shown if this code is revoked"
            />
          </div>
          <div className="sm:col-span-2">
            {error && <p className="mb-3 text-[12px] text-red-400">{error}</p>}
            <Button type="submit" disabled={creating || !label.trim()}>
              <KeyRound size={13} />
              {creating ? 'Generating…' : 'Generate code'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function EditForm({ code, onSaved, onCancel }) {
  const [label, setLabel] = useState(code.label)
  const [monthlyLimit, setMonthlyLimit] = useState(String(code.monthly_limit))
  const [organizationName, setOrganizationName] = useState(code.organization_name || '')
  const [contactMessage, setContactMessage] = useState(code.contact_message || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const updated = await adminApi.updateAccessCode(code.id, {
        label: label.trim(),
        monthly_limit: Number(monthlyLimit),
        organization_name: organizationName.trim() || null,
        contact_message: contactMessage.trim() || null,
      })
      onSaved(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div>
        <label className="mb-1 block text-[11px] text-admin-muted">Label</label>
        <Input value={label} onChange={(event) => setLabel(event.target.value)} />
      </div>
      <div>
        <label className="mb-1 block text-[11px] text-admin-muted">Monthly message limit</label>
        <Input type="number" min="0" value={monthlyLimit} onChange={(event) => setMonthlyLimit(event.target.value)} />
      </div>
      <div>
        <label className="mb-1 block text-[11px] text-admin-muted">Organization</label>
        <Input value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} />
      </div>
      <div>
        <label className="mb-1 block text-[11px] text-admin-muted">Replacement-code contact info</label>
        <Textarea rows={2} value={contactMessage} onChange={(event) => setContactMessage(event.target.value)} />
      </div>
      <div className="flex items-center gap-2 sm:col-span-2">
        {error && <p className="text-[12px] text-red-400">{error}</p>}
        <Button type="button" size="sm" onClick={save} disabled={saving || !label.trim()}>
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

function CodeRow({ code, onUpdated, busy, setBusy }) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState(null)

  async function toggleStatus() {
    setBusy(code.id)
    setError(null)
    try {
      const updated = code.status === 'revoked'
        ? await adminApi.reactivateAccessCode(code.id)
        : await adminApi.revokeAccessCode(code.id)
      onUpdated(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <article className="border-b border-admin-border last:border-0">
      <button
        onClick={() => setOpen((value) => !value)}
        className="grid w-full grid-cols-[1fr_auto_auto_auto_auto] items-center gap-4 px-4 py-3 text-left hover:bg-admin-hover"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-[13px] font-medium text-admin-text">{code.label}</span>
            <Badge variant={code.status === 'active' ? 'success' : 'error'}>{code.status}</Badge>
          </div>
          {code.organization_name && (
            <p className="mt-0.5 truncate text-[11px] text-admin-muted">{code.organization_name}</p>
          )}
        </div>
        <span className="whitespace-nowrap font-mono text-[11px] text-admin-muted">
          {code.usage_count} / {code.monthly_limit}
        </span>
        <span className="whitespace-nowrap text-[11px] text-admin-muted">Since {formatDate(code.period_start)}</span>
        <span className="whitespace-nowrap text-[11px] text-admin-muted">Created {formatDate(code.created_at)}</span>
        {open ? <ChevronUp size={13} className="text-admin-muted" /> : <ChevronDown size={13} className="text-admin-muted" />}
      </button>

      {open && (
        <div className="border-t border-admin-border bg-zinc-950/40 px-4 py-4">
          {editing ? (
            <EditForm
              code={code}
              onCancel={() => setEditing(false)}
              onSaved={(updated) => {
                onUpdated(updated)
                setEditing(false)
              }}
            />
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 text-[11px] text-admin-muted sm:grid-cols-4">
                <span>Created by <b className="text-admin-text">{code.created_by}</b></span>
                <span className="truncate">ID <b className="font-mono text-admin-text">{code.id}</b></span>
              </div>
              {code.contact_message && (
                <p className="mt-3 text-[12px] leading-5 text-admin-muted">
                  Replacement contact: {code.contact_message}
                </p>
              )}
              {error && <p className="mt-3 text-[12px] text-red-400">{error}</p>}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                  <Pencil size={12} /> Edit
                </Button>
                <Button
                  size="sm"
                  variant={code.status === 'revoked' ? 'default' : 'destructive'}
                  disabled={busy === code.id}
                  onClick={toggleStatus}
                >
                  {code.status === 'revoked' ? <RotateCcw size={12} /> : <ShieldOff size={12} />}
                  {code.status === 'revoked' ? 'Reactivate' : 'Revoke'}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </article>
  )
}

export default function AccessCodesPage() {
  const [status, setStatus] = useState('')
  const [data, setData] = useState({ items: [], total: 0 })
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const result = await adminApi.getAccessCodes({ status: status || undefined, offset, limit: PAGE_SIZE })
      setData(result)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [status, offset])

  useEffect(() => { load() }, [load])

  function replaceRow(updated) {
    setData((current) => ({
      ...current,
      items: current.items.map((item) => (item.id === updated.id ? updated : item)),
    }))
  }

  function handleCreated() {
    setStatus('')
    setOffset(0)
    load()
  }

  const pages = Math.ceil(data.total / PAGE_SIZE)
  const page = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="max-w-[1000px] p-6 font-admin">
      <div className="mb-5">
        <h1 className="m-0 text-lg font-semibold text-admin-text">Access Codes</h1>
        <p className="mt-1 text-xs text-admin-muted">
          Issue and manage the codes groups redeem for live chat access.
        </p>
      </div>

      <CreateForm onCreated={handleCreated} />

      <Card>
        <div className="flex gap-1 border-b border-admin-border px-2 pt-2">
          {TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => { setStatus(tab.value); setOffset(0) }}
              className={`border-b-2 px-3 py-2 text-[11px] ${status === tab.value ? 'border-admin-accent text-admin-text' : 'border-transparent text-admin-muted'}`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <CardContent className="p-0">
          {error && <p className="px-4 py-3 text-[12px] text-red-400">{error}</p>}
          {loading ? (
            <p className="py-12 text-center text-[12px] text-admin-muted">Loading…</p>
          ) : data.items.length === 0 ? (
            <p className="py-12 text-center text-[12px] text-admin-muted">No access codes yet.</p>
          ) : (
            data.items.map((code) => (
              <CodeRow key={code.id} code={code} onUpdated={replaceRow} busy={busy} setBusy={setBusy} />
            ))
          )}

          {pages > 1 && (
            <div className="flex items-center justify-between border-t border-admin-border px-4 py-3">
              <span className="text-[11px] text-admin-muted">Page {page} of {pages} · {data.total} codes</span>
              <div className="flex gap-2">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
                  className="rounded border border-admin-border px-3 py-1 text-[11px] text-admin-muted transition-colors hover:bg-admin-hover hover:text-admin-text disabled:opacity-40"
                >
                  ← Prev
                </button>
                <button
                  disabled={offset + PAGE_SIZE >= data.total}
                  onClick={() => setOffset((value) => value + PAGE_SIZE)}
                  className="rounded border border-admin-border px-3 py-1 text-[11px] text-admin-muted transition-colors hover:bg-admin-hover hover:text-admin-text disabled:opacity-40"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
