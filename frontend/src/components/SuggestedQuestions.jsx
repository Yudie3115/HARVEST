import { ArrowUpRight, LibraryBig, Route } from 'lucide-react'
import { Link } from 'react-router-dom'

function QuestionContent({ suggestion, index }) {
  const fromCatalogue = suggestion.kind === 'catalogue'
  return (
    <>
      <span className="followup-question__index">{String(index + 1).padStart(2, '0')}</span>
      <span className="followup-question__body">
        <span className="followup-question__text">{suggestion.text}</span>
        <span className="followup-question__kind">
          {fromCatalogue ? <LibraryBig size={11} /> : <Route size={11} />}
          {fromCatalogue ? 'Open reviewed catalogue answer' : 'Ask as a live follow-up'}
        </span>
      </span>
      <ArrowUpRight className="followup-question__arrow" size={15} aria-hidden="true" />
    </>
  )
}

export default function SuggestedQuestions({ questions, onAsk, disabled }) {
  if (!questions?.length) return null

  return (
    <section className="followup-panel" aria-labelledby="followup-heading">
      <div className="followup-panel__heading">
        <Route size={14} aria-hidden="true" />
        <span id="followup-heading">Continue the inquiry</span>
      </div>
      <div className="followup-panel__list">
        {questions.map((item, index) => {
          const suggestion = typeof item === 'string' ? { text: item, kind: 'generated' } : item
          const fromCatalogue = suggestion.kind === 'catalogue'
          if (fromCatalogue && suggestion.catalogue_entry_id) {
            return (
              <Link
                key={`${suggestion.text}-${index}`}
                to={`/catalogue/${suggestion.catalogue_entry_id}`}
                className="followup-question"
              >
                <QuestionContent suggestion={suggestion} index={index} />
              </Link>
            )
          }
          return (
            <button
              key={`${suggestion.text}-${index}`}
              type="button"
              onClick={() => onAsk?.(suggestion.text)}
              disabled={disabled}
              className="followup-question"
            >
              <QuestionContent suggestion={suggestion} index={index} />
            </button>
          )
        })}
      </div>
    </section>
  )
}
