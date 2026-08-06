/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        yeikar: {
          primary: {
            DEFAULT: '#D4AF37',
            light: '#E5C560',
            dark: '#A58421',
            glow: 'rgba(212, 175, 55, 0.15)',
          },
          secondary: {
            DEFAULT: '#2D1B10',
            light: '#422C1F',
            dark: '#1C0F08',
          },
          tertiary: {
            DEFAULT: '#F9F7F2',
            dark: '#EFECE6',
          },
          neutral: {
            DEFAULT: '#1A1A1A',
            light: '#2E2E2E',
            dark: '#0F0F0F',
          }
        }
      },
      fontFamily: {
        headline: ['"Hanken Grotesk"', 'sans-serif'],
         body: ['Manrope', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        '2xl': '16px',
        '3xl': '24px',
      },
      boxShadow: {
        subtle: '0 1px 2px 0 rgba(0, 0, 0, 0.02), 0 4px 12px 0 rgba(0, 0, 0, 0.03)',
        card: '0 1px 3px 0 rgba(26, 26, 26, 0.03), 0 8px 24px -6px rgba(45, 27, 16, 0.05)',
        lift: '0 12px 32px -8px rgba(26, 26, 26, 0.10), 0 4px 12px -2px rgba(45, 27, 16, 0.04)',
        gold: '0 4px 20px -2px rgba(212, 175, 55, 0.30)',
        modal: '0 24px 60px -12px rgba(15, 15, 15, 0.28)',
        shell: '0 16px 48px -24px rgba(15, 15, 15, 0.38)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.97)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.2s cubic-bezier(0.16, 1, 0.3, 1) both',
        'slide-up': 'slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) both',
        'scale-in': 'scale-in 0.25s cubic-bezier(0.16, 1, 0.3, 1) both',
      }
    },
  },
  plugins: [],
}
