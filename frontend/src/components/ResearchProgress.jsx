import { BookOpenCheck, BrainCircuit, Languages, Search, Sparkles } from 'lucide-react'

const STAGES = {
  preparing: {
    label: 'Preparing the research path',
    detail: 'Organising your question before retrieval.',
    icon: BrainCircuit,
  },
  language: {
    label: 'Reading language and context',
    detail: 'Interpreting the question in the conversation.',
    icon: Languages,
  },
  searching: {
    label: 'Searching the knowledge library',
    detail: 'Looking for the strongest evidence passages.',
    icon: Search,
  },
  reading_sources: {
    label: 'Reviewing the retrieved evidence',
    detail: 'Checking which passages can support the answer.',
    icon: BookOpenCheck,
  },
  synthesizing: {
    label: 'Working through the evidence',
    detail: 'Connecting findings into a clear, cited response.',
    icon: BrainCircuit,
  },
  followups: {
    label: 'Mapping useful next questions',
    detail: 'Finding related catalogue answers and research directions.',
    icon: Sparkles,
  },
}

const ORDER = ['preparing', 'language', 'searching', 'reading_sources', 'synthesizing', 'followups']

export default function ResearchProgress({ stage = 'preparing', sourceCount, compact = false }) {
  const current = STAGES[stage] || STAGES.preparing
  const Icon = current.icon
  const activeIndex = Math.max(0, ORDER.indexOf(stage))
  const detail =
    stage === 'reading_sources' && sourceCount
      ? `Reviewing ${sourceCount} relevant passage${sourceCount === 1 ? '' : 's'} for support.`
      : current.detail

  return (
    <div
      className={`research-progress ${compact ? 'research-progress--compact' : ''}`}
      role="status"
      aria-live="polite"
    >
      <div className="research-progress__signal" aria-hidden="true">
        <span className="research-progress__orbit" />
        <Icon size={compact ? 14 : 17} strokeWidth={1.7} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="research-progress__eyebrow">Research in progress</div>
        <div className="research-progress__label">{current.label}</div>
        {!compact && <div className="research-progress__detail">{detail}</div>}
        {!compact && (
          <div className="research-progress__track" aria-hidden="true">
            {ORDER.slice(0, -1).map((item, index) => (
              <span
                key={item}
                className={`research-progress__step ${
                  index <= activeIndex ? 'research-progress__step--active' : ''
                }`}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
