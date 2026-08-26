"use client";

import { useSearchParams } from "next/navigation";

import { authClient } from "@/lib/auth-client";

export function LoginForm() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");
  const errorDescription = searchParams.get("error_description");
  const nextPath = searchParams.get("next");
  const callbackURL = nextPath?.startsWith("/") ? nextPath : "/projects";

  return (
    <div className="mt-8">
      {error ? (
        <p className="mb-4 rounded-md border border-red-500/30 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          {errorDescription ||
            (error === "unauthorized_email"
              ? "Este email não está autorizado a acessar o SceneCraft."
              : "Não foi possível entrar. Tente de novo.")}
        </p>
      ) : null}
      <button
        type="button"
        onClick={() => authClient.signIn.social({ provider: "google", callbackURL })}
        className="flex w-full items-center justify-center gap-2 rounded-md bg-brass-500 px-3 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400"
      >
        <GoogleMark />
        Entrar com Google
      </button>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M21.6 12.23c0-.76-.07-1.49-.2-2.19H12v4.14h5.38a4.6 4.6 0 0 1-2 3.02v2.5h3.23c1.89-1.74 2.99-4.3 2.99-7.47Z" />
      <path d="M12 22c2.7 0 4.96-.89 6.62-2.42l-3.23-2.5c-.9.6-2.04.96-3.39.96-2.6 0-4.81-1.76-5.6-4.12H3.06v2.59A10 10 0 0 0 12 22Z" />
      <path d="M6.4 13.92A6.01 6.01 0 0 1 6.08 12c0-.67.12-1.31.32-1.92V7.49H3.06A10 10 0 0 0 2 12c0 1.61.38 3.14 1.06 4.51l3.34-2.59Z" />
      <path d="M12 5.96c1.47 0 2.78.5 3.82 1.5l2.86-2.86C16.95 2.96 14.7 2 12 2A10 10 0 0 0 3.06 7.49l3.34 2.59C7.19 7.72 9.4 5.96 12 5.96Z" />
    </svg>
  );
}
