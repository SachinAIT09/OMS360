/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin when the UI is hosted separately (e.g. Netlify), such as https://oms360-api.onrender.com. Empty = same origin. */
  readonly VITE_API_URL?: string;
}
