/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "../../packages/ui-legal/src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: '#111827',
        muted: '#667085',
        background: '#F6F8FC',
        surface: '#FFFFFF',
        border: '#DCE3ED',
        primary: '#2557D6',
        'primary-hover': '#1E46B8',
        'primary-soft': '#E8EEFB',
        accent: '#E85D0F',
        'accent-soft': '#FFF4ED',
        success: '#168A45',
        'success-soft': '#E8F7EE',
        warning: '#B54708',
        'warning-soft': '#FEF4E6',
        // aliases used across pages
        brand: '#E85D0F',
        brandDark: '#C24A0A',
        brandLight: '#FFF4ED',
        civic: '#2557D6',
        civicDark: '#1E46B8',
        civicSoft: '#E8EEFB',
        trust: '#168A45',
        trustSoft: '#E8F7EE',
      },
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'Inter', 'system-ui', 'sans-serif'],
        display: ['"Be Vietnam Pro"', 'Inter', 'system-ui', 'sans-serif'],
      },
      maxWidth: {
        content: '1200px',
        chat: '1120px',
        bubble: '760px',
      },
      borderRadius: {
        card: '16px',
        control: '14px',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(17, 24, 39, 0.04), 0 8px 24px -12px rgba(37, 87, 214, 0.12)',
        lift: '0 2px 8px rgba(17, 24, 39, 0.06)',
      },
      transitionDuration: {
        ui: '200ms',
      },
      minHeight: {
        touch: '48px',
        search: '64px',
      },
    },
  },
  plugins: [],
}
