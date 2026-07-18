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
        'primary-dark': '#1E46B8',
        accent: '#E85D0F',
        'accent-soft': '#FFF4ED',
        brand: '#E85D0F',
        brandDark: '#C24A0A',
        brandLight: '#FFF4ED',
        civic: '#2557D6',
        civicDark: '#1E46B8',
        civicSoft: '#E8EEFB',
        trust: '#168A45',
        trustSoft: '#E8F7EE',
        destructive: '#DC2626',
        success: '#168A45',
        'success-soft': '#E8F7EE',
        warning: '#B54708',
        'warning-soft': '#FEF4E6',
        secondaryAccent: '#2557D6',
      },
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'Inter', 'system-ui', 'sans-serif'],
        display: ['"Be Vietnam Pro"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      maxWidth: {
        content: '1200px',
        chat: '1120px',
        bubble: '760px',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(17, 24, 39, 0.04), 0 8px 24px -12px rgba(37, 87, 214, 0.12)',
        card: '0 2px 8px rgba(17, 24, 39, 0.06), 0 16px 40px -20px rgba(37, 87, 214, 0.2)',
        lift: '0 2px 8px rgba(17, 24, 39, 0.06)',
      },
      borderRadius: {
        card: '16px',
        control: '14px',
      },
      minHeight: {
        touch: '48px',
        search: '64px',
      },
      transitionDuration: {
        ui: '200ms',
      },
      backgroundImage: {
        'gradient-accent': 'linear-gradient(135deg, #2557D6, #E85D0F)',
        'gradient-info': 'linear-gradient(135deg, #1E46B8, #4F7FE8)',
        'gradient-success': 'linear-gradient(135deg, #168A45, #34C759)',
        'gradient-warning': 'linear-gradient(135deg, #B54708, #E85D0F)',
        'gradient-danger': 'linear-gradient(135deg, #DC2626, #F87171)',
        'gradient-dark': 'linear-gradient(135deg, #0F172A, #2557D6)',
      },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.45s cubic-bezier(0.22, 1, 0.36, 1) forwards',
      },
    },
  },
  plugins: [],
};
