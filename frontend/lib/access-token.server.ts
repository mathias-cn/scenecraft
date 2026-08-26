import { cache } from "react";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

type TokenResult = {
  token?: string;
};

async function readServerToken(): Promise<string | null> {
  const requestHeaders = headers();
  const session = await auth.api.getSession({ headers: requestHeaders });
  if (!session) {
    return null;
  }
  const result = (await auth.api.getToken({ headers: requestHeaders })) as TokenResult | null;
  return result?.token ?? null;
}

/** JWT da sessão do request atual. Sem sessão, redireciona para /login. */
export const getServerAccessToken = cache(async (): Promise<string> => {
  const token = await readServerToken();
  if (!token) {
    redirect("/login");
  }
  return token;
});
