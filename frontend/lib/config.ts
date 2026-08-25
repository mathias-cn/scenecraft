/** Base URL do FastAPI. Definida em `NEXT_PUBLIC_API_URL` (ver `.env.example`). */
export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return raw.replace(/\/+$/, "");
}
