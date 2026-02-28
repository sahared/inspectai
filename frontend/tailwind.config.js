/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#EFF6FF",
          500: "#1A56DB",
          600: "#1648C0",
          700: "#1240A8",
        },
      },
    },
  },
  plugins: [],
};
