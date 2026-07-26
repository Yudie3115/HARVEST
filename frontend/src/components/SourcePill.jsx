import { ArrowRight, FileText } from 'lucide-react'

export default function SourcePill({ sources, onOpen }) {
  if (!sources?.length) return null

  return (
    <div className="source-preview">
      <div className="source-preview__label">
        <FileText size={12} />
        Evidence used
      </div>
      <div className="source-preview__files">
        {sources.slice(0, 2).map((source, index) => (
          <span className="source-preview__file" key={`${source.document_id || source.url}-${index}`}>
            <span className="source-preview__citation">
              {(source.citation_indices || [index + 1]).map((number) => `[${number}]`).join(' ')}
            </span>
            {source.title || 'Research source'}
          </span>
        ))}
      </div>
      <button
        onClick={() => onOpen(sources)}
        className="source-preview__open"
        aria-label={`View ${sources.length} source${sources.length !== 1 ? 's' : ''}`}
      >
        Review all {sources.length}
        <ArrowRight size={12} />
      </button>
    </div>
  )
}
