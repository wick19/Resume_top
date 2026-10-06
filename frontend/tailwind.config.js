/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#eef3fb",
        card: "#f7f9fc",
        ink: "#0c1224",
        muted: "#5c6b82",
        primary: "#0040f0",
        accent: "#00a0f0",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 18px 50px rgba(12, 18, 36, 0.08)",
      },
    },
  },
  plugins: [],
};
