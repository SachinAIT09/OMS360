/* Tailwind for layout and custom styling alongside Mantine (which keeps its components and its CSS reset).
   - preflight is off, so Mantine's reset and component styles are untouched;
   - dark: follows Mantine's colour scheme (data-mantine-color-scheme on <html>);
   - colours, radii, spacing and fonts point at Mantine's CSS variables, so both systems share one theme. */
import type { Config } from "tailwindcss";
import { EF, MARK, SEV } from "./src/lib/colors";

const scale = (name: string) => Object.fromEntries(Array.from({ length: 10 }, (_, i) => [i, `var(--mantine-color-${name}-${i})`]));

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  corePlugins: { preflight: false },
  darkMode: ["variant", "&:is([data-mantine-color-scheme=\"dark\"] *)"],
  theme: {
    extend: {
      colors: {
        brand: scale("brand"), ai: scale("ai"), navy: scale("dark"),
        sev: SEV, ef: Object.fromEntries(EF.map((c, i) => [i, c])), mark: MARK,
        body: "var(--mantine-color-body)", text: "var(--mantine-color-text)", dimmed: "var(--mantine-color-dimmed)",
        line: "var(--mantine-color-default-border)",
      },
      fontFamily: { sans: "var(--mantine-font-family)" },
      borderRadius: { "m-sm": "var(--mantine-radius-sm)", "m-md": "var(--mantine-radius-md)", "m-lg": "var(--mantine-radius-lg)" },
      spacing: { "m-xs": "var(--mantine-spacing-xs)", "m-sm": "var(--mantine-spacing-sm)", "m-md": "var(--mantine-spacing-md)", "m-lg": "var(--mantine-spacing-lg)" },
      letterSpacing: { label: ".06em", caps: ".08em" },
    },
  },
} satisfies Config;
