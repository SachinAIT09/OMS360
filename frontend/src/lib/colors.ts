/* Status and data colours, defined once. Used by TypeScript (map layers, chart series and inline data bars need real values)
   and by tailwind.config.ts (utility classes such as bg-sev-crit). Theme colours (brand, ai, navy) live in theme.ts. */

/** Severity scale shared by outage shares, equipment health and storm hazard. */
export const SEV = { ok: "#3ec46d", watch: "#f5a623", high: "#f07a2e", crit: "#e0506a", unknown: "#8a9aa5" } as const;

/** Enhanced Fujita colours for tornado damage paths, EF0 … EF5. */
export const EF = ["#8fd16a", "#f5d33b", "#f5a623", "#f07a2e", "#e0506a", "#b04fd8"] as const;

/** Map markers. */
export const MARK = { outage: "#ff3b6b", yard: "#2b6bff" } as const;
