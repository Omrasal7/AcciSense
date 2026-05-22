export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        signal: "#ef4444",
        ember: "#f97316",
        field: "#e2e8f0",
        skyline: "#0ea5e9",
      },
      fontFamily: {
        sans: ["Poppins", "ui-sans-serif", "system-ui"],
      },
      boxShadow: {
        panel: "0 18px 60px rgba(15, 23, 42, 0.12)",
      },
    },
  },
  plugins: [],
};
