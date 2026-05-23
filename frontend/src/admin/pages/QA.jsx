import { useState } from 'react'
import { Loader2, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Textarea } from '../../components/ui/input'
import { Button } from '../../components/ui/button'
import { Card, CardContent } from '../../components/ui/card'
import { Alert } from '../../components/ui/alert'
import { Progress } from '../../components/ui/progress'
import { adminApi } from '../api'

export default function QAPage() {
  const [question, setQuestion] = useState('')
  const [topK, setTopK] = useState(8)
  const [threshold, setThreshold] = useState(0.4)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(null)

  async function handleAsk(e) {
    e.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    setExpanded(null)
    try {
      const data = await adminApi.qa(question.trim(), topK, threshold)
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6 font-admin max-w-[860px]">
      <div className="mb-5">
        <h1 className="text-lg font-semibold text-admin-text">Knowledge Q&A</h1>
        <p className="text-xs text-admin-muted mt-0.5">Ask a question — the AI searches the knowledge base and synthesises a grounded answer</p>
      </div>

      <form onSubmit={handleAsk} className="space-y-3 mb-5">
        <Textarea
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder="e.g. What are best practices for maize storage after harvest?"
          rows={3}
        />

        {/* Filters collapsible */}
        <div>
          <button
            type="button"
            onClick={() => setFiltersOpen(!filtersOpen)}
            className="flex items-center gap-1.5 text-[11px] text-admin-muted hover:text-admin-text transition-colors"
          >
            {filtersOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            Search filters
          </button>
          {filtersOpen && (
            <div className="mt-3 grid grid-cols-2 gap-4 bg-admin-surface border border-admin-border rounded-md p-4">
              <div>
                <label className="block text-[10px] font-medium text-admin-muted uppercase tracking-wider mb-2">
                  Top-K chunks: <span className="text-admin-text font-mono">{topK}</span>
                </label>
                <input
                  type="range" min={3} max={15} step={1}
                  value={topK}
                  onChange={e => setTopK(Number(e.target.value))}
                  className="w-full accent-admin-accent"
                />
              </div>
              <div>
                <label className="block text-[10px] font-medium text-admin-muted uppercase tracking-wider mb-2">
                  Min similarity: <span className="text-admin-text font-mono">{threshold.toFixed(2)}</span>
                </label>
                <input
                  type="range" min={0} max={0.9} step={0.05}
                  value={threshold}
                  onChange={e => setThreshold(Number(e.target.value))}
                  className="w-full accent-admin-accent"
                />
              </div>
            </div>
          )}
        </div>

        <Button type="submit" disabled={loading || !question.trim()} className="w-full sm:w-auto">
          {loading && <Loader2 size={13} className="animate-spin" />}
          {loading ? 'Searching knowledge base…' : 'Ask the Knowledge Base'}
        </Button>
      </form>

      {error && (
        <Alert variant="error" className="mb-4">{error}</Alert>
      )}

      {result?.reason === 'no_results' && (
        <Alert variant="warning" className="mb-4">
          No relevant chunks found above the similarity threshold. Try lowering the minimum similarity score or rephrasing your question.
        </Alert>
      )}

      {result?.answer && (
        <div className="space-y-4 animate-fade-up">
          {/* Answer */}
          <Alert variant="success">
            <div className="text-[11px] font-semibold text-green-400 uppercase tracking-wider mb-2">Answer</div>
            <div className="prose prose-sm prose-invert max-w-none text-[13px] text-green-100/90">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {result.answer || result.response || '(no answer returned)'}
              </ReactMarkdown>
            </div>
          </Alert>

          {/* Sources */}
          {result.sources?.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-admin-muted uppercase tracking-wider mb-2">
                Sources ({result.sources.length} chunks)
              </p>
              <div className="space-y-2">
                {result.sources.map((src, i) => {
                  const payload = src.payload || src
                  const score = src.score || 0
                  const isOpen = expanded === i
                  const url = payload.source_url || '—'
                  return (
                    <Card key={i}>
                      <div
                        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-admin-hover rounded-lg transition-colors"
                        onClick={() => setExpanded(isOpen ? null : i)}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="text-[11px] font-mono text-admin-muted">[{i + 1}]</span>
                          <Progress value={score} className="w-20" />
                          <span className="font-mono text-[11px] text-admin-muted">{score.toFixed(3)}</span>
                          <span className="text-[12px] text-admin-text truncate">{url}</span>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <a href={url} target="_blank" rel="noopener noreferrer"
                            className="text-admin-muted hover:text-admin-accent"
                            onClick={e => e.stopPropagation()}>
                            <ExternalLink size={11} />
                          </a>
                          {isOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                        </div>
                      </div>
                      {isOpen && (
                        <CardContent className="pt-0 border-t border-admin-border">
                          <p className="text-[12px] text-zinc-300 leading-relaxed mb-3 whitespace-pre-wrap">
                            {payload.text || '(no text)'}
                          </p>
                          <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-admin-muted">
                            {payload.topics?.length > 0 && <span>Topics: {payload.topics.join(', ')}</span>}
                            {payload.crops?.length > 0 && <span>Crops: {payload.crops.join(', ')}</span>}
                            {payload.document_type && <span>Type: {payload.document_type}</span>}
                          </div>
                        </CardContent>
                      )}
                    </Card>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
