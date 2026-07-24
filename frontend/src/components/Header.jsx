import { NavLink } from 'react-router-dom'

const navLinkStyle = ({ isActive }) => ({
  fontFamily: 'Outfit, system-ui, sans-serif',
  fontSize: 13,
  fontWeight: 500,
  color: isActive ? '#8ecfaa' : '#d4cfc6',
  textDecoration: 'none',
  padding: '4px 2px',
  borderBottom: isActive ? '1px solid #6ab08a' : '1px solid transparent',
})

export default function Header() {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '8px',
        padding: '12px 16px',
        borderBottom: '1px solid #1e2a1e',
        background: 'rgba(14,20,17,0.96)',
        backdropFilter: 'blur(8px)',
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: '#1e3a28',
            border: '1px solid #3d6b4f',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16,
          }}
        >
          🌾
        </div>
        <div>
          <span
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontSize: 17,
              color: '#e8e4da',
              letterSpacing: '-0.3px',
            }}
          >
            PostHarvest
          </span>
          <span
            style={{
              fontFamily: 'Fraunces, Georgia, serif',
              fontSize: 17,
              color: '#d4a853',
              fontStyle: 'italic',
              marginLeft: 5,
            }}
          >
            AI
          </span>
        </div>
      </div>

      <nav style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <NavLink to="/" end style={navLinkStyle}>
          Ask
        </NavLink>
        <NavLink to="/documents" style={navLinkStyle}>
          Documents
        </NavLink>
        <NavLink to="/catalogue" style={navLinkStyle}>
          Catalogue
        </NavLink>
      </nav>
    </header>
  )
}
