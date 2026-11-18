/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: { colors: { maskx: { bg:'#080808', surface:'#101010', panel:'#171717', red:'#E60023', bright:'#FF263D', line:'#303030' } }, fontFamily: { mono:['IBM Plex Mono','monospace'] } } },
  plugins: []
}
