import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1.5rem", screens: { "2xl": "1280px" } },
    extend: {
      colors: {
        paper: "rgb(var(--paper) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        subtle: "rgb(var(--subtle) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-ink": "rgb(var(--accent-ink) / <alpha-value>)",
        danger: "rgb(var(--danger) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        good: "rgb(var(--good) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
        display: ["var(--font-instrument)", "ui-serif", "Georgia"],
      },
      fontVariantNumeric: { tabular: "tabular-nums" },
      borderRadius: { xs: "4px", sm: "6px", DEFAULT: "8px", lg: "12px", xl: "16px" },
      boxShadow: {
        soft: "0 1px 0 rgb(0 0 0 / 0.02), 0 1px 2px rgb(0 0 0 / 0.04)",
      },
      keyframes: {
        pulseSoft: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.55" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        in: { "0%": { opacity: "0", transform: "translateY(4px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
      },
      animation: {
        pulseSoft: "pulseSoft 1.6s cubic-bezier(.4,0,.6,1) infinite",
        shimmer: "shimmer 1.8s linear infinite",
        in: "in 160ms ease-out both",
      },
    },
  },
  plugins: [],
};
export default config;
