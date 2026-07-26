import { useEffect } from 'react'
import {
  ArrowUpRight,
  BookOpenText,
  ExternalLink,
  FileText,
  ShieldCheck,
  X,
} from 'lucide-react'
import { isSafeUrl } from '../lib/sanitize'

function humanize(value) {
  return value
    ? value.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())
    : null
}

function citationLabel(source, index) {
  const indices = source.citation_indices?.length ? source.citation_indices : [index + 1]
  return indices.map((number) => `[${number}]`).join(' ')
}

function SourceCard({ source, index }) {
  const externalIsSafe = isSafeUrl(source.url)
  const internalIsSafe = source.library_url?.startsWith('/documents/')

  return (
    <article className="research-source">
      <div className="research-source__topline">
        <span className="research-source__citation">{citationLabel(source, index)}</span>
        <span className="research-source__origin">
          {humanize(source.site_name) || 'Knowledge library'}
        </span>
        {source.score != null && (
          <span className="research-source__score" title="Semantic retrieval relevance">
            {Math.round(source.score * 100)}% relevance
          </span>
        )}
      </div>

      <div className="research-source__title-row">
        <span className="research-source__file-icon" aria-hidden="true">
          <FileText size={17} strokeWidth={1.6} />
        </span>
        <div>
          <h3>{source.title || 'Untitled research source'}</h3>
          {source.document_type && <p>{humanize(source.document_type)}</p>}
        </div>
      </div>

      {source.summary && (
        <div className="research-source__brief">
          <span>Document brief</span>
          <p>{source.summary}</p>
        </div>
      )}

      {source.snippet && (
        <details className="research-source__excerpt">
          <summary>View the cited passage</summary>
          <blockquote>{source.snippet}</blockquote>
        </details>
      )}

      {source.topics?.length > 0 && (
        <div className="research-source__topics">
          {source.topics.slice(0, 4).map((topic) => (
            <span key={topic}>{humanize(topic)}</span>
          ))}
        </div>
      )}

      {(internalIsSafe || externalIsSafe) && (
        <div className="research-source__actions">
          {internalIsSafe && (
            <a href={source.library_url}>
              <BookOpenText size={13} />
              Open document brief
              <ArrowUpRight size={12} />
            </a>
          )}
          {externalIsSafe && (
            <a href={source.url} target="_blank" rel="noopener noreferrer">
              <ExternalLink size={13} />
              Original source
            </a>
          )}
        </div>
      )}
    </article>
  )
}

export default function SourcesSidebar({ sources, onClose }) {
  const isOpen = !!sources?.length

  useEffect(() => {
    if (!isOpen) return undefined
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [isOpen, onClose])

  return (
    <>
      <button
        type="button"
        aria-label="Close research references"
        aria-hidden={!isOpen}
        tabIndex={isOpen ? 0 : -1}
        disabled={!isOpen}
        onClick={onClose}
        className={`research-drawer__backdrop ${isOpen ? 'research-drawer__backdrop--open' : ''}`}
      />
      <aside
        className={`research-drawer ${isOpen ? 'research-drawer--open' : ''}`}
        aria-hidden={!isOpen}
        aria-label="Research references"
      >
        <header className="research-drawer__header">
          <div className="research-drawer__heading">
            <span className="research-drawer__icon">
              <BookOpenText size={18} strokeWidth={1.6} />
            </span>
            <div>
              <span>Evidence notebook</span>
              <h2>Research references</h2>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close research references">
            <X size={18} />
          </button>
        </header>

        <div className="research-drawer__context">
          <ShieldCheck size={15} aria-hidden="true" />
          <p>
            These are the documents and passages used to construct the answer. Citation numbers
            correspond to markers in the response.
          </p>
        </div>

        <div className="research-drawer__list">
          {sources?.map((source, index) => (
            <SourceCard
              key={`${source.document_id || source.url || 'source'}-${index}`}
              source={source}
              index={index}
            />
          ))}
        </div>

        <footer className="research-drawer__footer">
          <span>{sources?.length || 0} referenced document{sources?.length === 1 ? '' : 's'}</span>
          <span>Verify critical decisions against the original publication.</span>
        </footer>
      </aside>
    </>
  )
}
