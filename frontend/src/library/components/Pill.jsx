// Small non-interactive badge/pill used across the detail page for the
// category badge, topic/crop/region tags, and the actionable/has_data
// status badges. Not clickable — display only (filtering pills with click
// behavior live in FacetPills, which is a different, interactive component).
const VARIANTS = {
  muted: { border: '#2a3329', background: '#0f1a12', color: '#8a9489' },
  gold: { border: '#d4a853', background: 'transparent', color: '#d4a853' },
  green: { border: '#3d6b4f', background: '#1e3a28', color: '#8ecfaa' },
}

export default function Pill({ children, variant = 'muted' }) {
  const { border, background, color } = VARIANTS[variant] || VARIANTS.muted
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 9px',
        borderRadius: 999,
        border: `1px solid ${border}`,
        background,
        color,
        fontSize: 11,
        fontFamily: '"IBM Plex Mono", monospace',
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </span>
  )
}
