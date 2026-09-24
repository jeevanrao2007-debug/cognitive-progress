import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["system-ui", "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "Roboto", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        // Core brand
        ink: "#1F2328",
        sand: "#F6F8FA",
        ember: "#D97706",
        moss: "#0D9488",
        // Explicit palette — no Tailwind JIT guessing
        midnight: "#0D1117",
        surface: "#FFFFFF",
        muted: "#F6F8FA",
        faint: "#EAEEF2",
        border: "#D0D7DE",
        "border-dark": "#30363D",
        // Text
        "text-primary": "#1F2328",
        "text-secondary": "#656D76",
        "text-muted": "#8C959F",
        // Semantic
        success: "#1A7F37",
        "success-subtle": "#DAFBE1",
        "success-border": "#82E9A6",
        danger: "#CF222E",
        "danger-subtle": "#FFEBE9",
        "danger-border": "#FF9EA0",
        attention: "#9A6700",
        "attention-subtle": "#FFF8C5",
        "attention-border": "#EAC54F",
        accent: "#0969DA",
        "accent-subtle": "#DFF0FF",
        "accent-border": "#54AEFF",
        // Header dark
        "header-bg": "#0D1117",
        "header-border": "#30363D",
        "header-fg": "#F0F6FC",
        "header-muted": "#848D97",
        "header-subtle": "#21262D",
      },
      boxShadow: {
        card: "0 1px 3px rgba(31, 35, 40, 0.06), 0 0 0 1px rgba(31, 35, 40, 0.08)",
        "card-hover": "0 3px 12px rgba(31, 35, 40, 0.12), 0 0 0 1px rgba(31, 35, 40, 0.10)",
        header: "0 1px 0 rgba(31, 35, 40, 0.1)",
        panel: "0 1px 3px rgba(31, 35, 40, 0.06), 0 0 0 1px rgba(31, 35, 40, 0.08)",
      },
    },
  },
  plugins: [],
} satisfies Config;
