import { useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { adminApi } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'

function Row({ label, value, mono }) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-admin-border last:border-0">
      <span className="text-[12px] text-admin-muted">{label}</span>
      <span
        className={[
          'text-[12px] text-admin-text text-right max-w-[60%] break-all',
          mono ? 'font-mono' : '',
        ].join(' ')}
      >
        {String(value)}
      </span>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <Card className="animate-fade-up">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {children}
      </CardContent>
    </Card>
  )
}

export default function ConfigPage() {
  const [config, setConfig] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    adminApi.getConfig()
      .then(setConfig)
      .catch(e => setError(e.message))
  }, [])

  if (error) {
    return (
      <div className="p-6 font-admin">
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    )
  }

  return (
    <div className="p-6 font-admin max-w-[800px]">
      <div className="mb-5">
        <h1 className="text-lg font-semibold text-admin-text">Configuration</h1>
        <p className="text-xs text-admin-muted mt-0.5">Read-only snapshot of current settings</p>
      </div>

      {/* Read-only banner */}
      <div className="flex items-center gap-2.5 bg-yellow-500/5 border border-yellow-500/20 rounded-md px-4 py-3 mb-5 text-[12px] text-yellow-300">
        <AlertTriangle size={13} className="flex-shrink-0" />
        Edit <code className="font-mono bg-yellow-500/10 px-1 rounded">.env</code> and restart services to change settings. Credential changes require an API container restart only.
      </div>

      {config ? (
        <div className="grid gap-3">
          <Section title="LLM">
            <Row label="Provider" value={config.llm.provider} />
            <Row label="Model" value={config.llm.model} mono />
            <Row label="Temperature" value={config.llm.temperature} mono />
            <Row label="Max tokens" value={config.llm.max_tokens} mono />
            <Row label="OpenAI API key" value={config.llm.openai_api_key} mono />
          </Section>

          <Section title="Crawl">
            <Row label="Max depth" value={config.crawl.max_depth} mono />
            <Row label="Delay (seconds)" value={config.crawl.delay_seconds} mono />
            <Row label="Relevance threshold" value={config.crawl.relevance_threshold} mono />
            <Row label="Chunk size" value={config.crawl.chunk_size} mono />
            <Row label="Chunk overlap" value={config.crawl.chunk_overlap} mono />
          </Section>

          <Section title="Services">
            <Row label="Database URL" value={config.services.database_url} mono />
            <Row label="Qdrant URL" value={config.services.qdrant_url} mono />
            <Row label="MinIO endpoint" value={config.services.minio_endpoint} mono />
            <Row label="Prefect API URL" value={config.services.prefect_api_url} mono />
            <Row label="Sunbird AI URL" value={config.services.sunbird_api_url} mono />
            <Row label="Translation enabled" value={String(config.services.translation_enabled)} />
          </Section>

          <Section title="Sites">
            {Object.entries(config.sites).map(([site, enabled]) => (
              <Row key={site} label={site} value={enabled ? 'enabled' : 'disabled'} />
            ))}
          </Section>

          <Section title="Environment">
            <Row label="Environment" value={config.environment} />
          </Section>
        </div>
      ) : (
        <div className="text-[12px] text-admin-muted">Loading…</div>
      )}
    </div>
  )
}
