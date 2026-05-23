/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        body: ['Outfit', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
        admin: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        'admin-bg': '#09090b',
        'admin-surface': '#111111',
        'admin-border': '#1f1f1f',
        'admin-hover': '#1a1a1a',
        'admin-active': '#222222',
        'admin-text': '#f4f4f5',
        'admin-muted': '#71717a',
        'admin-accent': '#22c55e',
        'admin-accent-dim': '#16a34a',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-up': 'fadeUp 0.3s ease-out both',
      },
    },
  },
  plugins: [],
}
