/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: '#0ea5e9', dark: '#0369a1' },
      },
    },
  },
  plugins: [],
};
