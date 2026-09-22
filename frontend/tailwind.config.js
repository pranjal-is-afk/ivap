/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // IBVAP command-center palette — near-black slate, not "AI startup" purple
        ink: {
          950: '#07090c',
          900: '#0b0e13',
          850: '#10141b',
          800: '#151a23',
          700: '#1d2430',
          600: '#2a3342',
          500: '#3d4959',
        },
        grid: '#1a212c',
        alert: {
          critical: '#ff3b30',
          high: '#ff6a3d',
          medium: '#ffb340',
          low: '#3f8cff',
        },
        signal: {
          ok: '#2fd67b',
          warn: '#ffb340',
          bad: '#ff3b30',
          idle: '#5b6b7f',
        },
      },
      fontFamily: {
        mono: ['"IBM Plex Mono"', '"JetBrains Mono"', 'Consolas', 'monospace'],
        sans: ['"IBM Plex Sans"', 'Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
    },
  },
  plugins: [],
}
