/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#ffe5e5",
          500: "#ff3b30", // nostalgic red
        },
      },
    },
  },
  plugins: [],
};