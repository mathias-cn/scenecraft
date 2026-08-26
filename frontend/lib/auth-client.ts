import { jwtClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";

export const authClient = createAuthClient({
  plugins: [jwtClient()],
});

type TokenResponse = {
  token?: string;
};

let cachedToken: { value: string; expiresAt: number } | null = null;

function readJwtExpiry(token: string): number {
  try {
    const payload = token.split(".")[1];
    if (!payload) {
      return 0;
    }
    const json = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as {
      exp?: number;
    };
    return typeof json.exp === "number" ? json.exp * 1000 : 0;
  } catch {
    return 0;
  }
}

/** JWT da sessão atual, ou `null` se não houver sessão. */
export async function getSessionToken(): Promise<string | null> {
  const now = Date.now();
  if (cachedToken && cachedToken.expiresAt - 30_000 > now) {
    return cachedToken.value;
  }

  const result = await authClient.token();
  if (result.error) {
    cachedToken = null;
    return null;
  }
  const token = (result.data as TokenResponse | null)?.token;
  if (!token) {
    cachedToken = null;
    return null;
  }

  const expiresAt = readJwtExpiry(token) || now + 60_000;
  cachedToken = { value: token, expiresAt };
  return token;
}

export function clearSessionTokenCache(): void {
  cachedToken = null;
}
