import { createTheme, type MantineColorsTuple } from "@mantine/core";

const brand: MantineColorsTuple = ["#e8efff", "#cfdcff", "#9db8ff", "#6a92ff", "#3f71ff", "#2b6bff", "#1a5aef", "#0f48d4", "#073fbe", "#0034a8"];
const ai: MantineColorsTuple = ["#f1ecff", "#dcd2ff", "#c3b1ff", "#a68cfa", "#8f6ff5", "#7c5cf0", "#6c4bdf", "#5b3cc6", "#4f33b0", "#41299a"];
// Deep navy dark palette — operations-center look
const dark: MantineColorsTuple = ["#d5dcf0", "#aeb9d8", "#8a96c0", "#5d6a94", "#2a3a6e", "#1c2a58", "#121d42", "#0b1532", "#081027", "#050b1d"];

const FONT = "\"Plus Jakarta Sans\", -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Oxygen, Ubuntu, Cantarell, \"Fira Sans\", \"Droid Sans\", \"Helvetica Neue\", sans-serif";

export const theme = createTheme({
  primaryColor: "brand",
  colors: { brand, ai, dark },
  fontFamily: FONT,
  headings: { fontFamily: FONT, fontWeight: "600" },
  defaultRadius: "md",
  cursorType: "pointer",
  components: {
    Card: { defaultProps: { withBorder: true, radius: "md", padding: "md" } },
    Paper: { defaultProps: { radius: "md" } },
    Badge: { defaultProps: { radius: "sm", variant: "light" } },
    Table: { defaultProps: { verticalSpacing: "xs", highlightOnHover: true } },
    Button: { defaultProps: { radius: "md" } },
    Modal: { defaultProps: { centered: true, radius: "md" } },
    Drawer: { defaultProps: { position: "right", size: "lg" } },
    Tooltip: { defaultProps: { withArrow: true } },
  },
});
