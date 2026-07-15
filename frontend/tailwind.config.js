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
        body: ['Inter', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      }
    },
  },
  plugins: [],
}
