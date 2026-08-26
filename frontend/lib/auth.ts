import { betterAuth } from "better-auth";
import { APIError } from "better-auth/api";
import { nextCookies } from "better-auth/next-js";
import { jwt } from "better-auth/plugins";
import { Pool } from "pg";

const UNAUTHORIZED_EMAIL_MESSAGE =
  "Este email não está autorizado a acessar o SceneCraft.";

function ownerEmail(): string {
  return (process.env.OWNER_EMAIL ?? "").trim().toLowerCase();
}

function isOwnerEmail(email: string | null | undefined): boolean {
  const allowed = ownerEmail();
  if (!allowed) {
    return false;
  }
  return (email ?? "").trim().toLowerCase() === allowed;
}

function rejectUnauthorizedEmail(email: string | null | undefined): void {
  if (isOwnerEmail(email)) {
    return;
  }
  throw new APIError("FORBIDDEN", {
    message: UNAUTHORIZED_EMAIL_MESSAGE,
    code: "UNAUTHORIZED_EMAIL",
  });
}

function authDatabaseUrl(): string {
  const url = process.env.DATABASE_URL_MIGRATIONS || process.env.DATABASE_URL;
  if (url) {
    return url;
  }
  if (process.env.NEXT_PHASE === "phase-production-build") {
    return "postgresql://127.0.0.1:5432/build";
  }
  throw new Error("DATABASE_URL is required for Better Auth");
}

const globalForPg = globalThis as typeof globalThis & { authPool?: Pool };

function getAuthPool(): Pool {
  if (!globalForPg.authPool) {
    globalForPg.authPool = new Pool({
      connectionString: authDatabaseUrl(),
      max: 3,
    });
  }
  return globalForPg.authPool;
}

export const auth = betterAuth({
  appName: "SceneCraft",
  baseURL: process.env.BETTER_AUTH_URL,
  secret: process.env.BETTER_AUTH_SECRET,
  database: getAuthPool(),
  trustedOrigins: [
    process.env.BETTER_AUTH_URL,
    "http://localhost:3000",
    "https://scenecraft.mazting.studio",
  ].filter((origin): origin is string => Boolean(origin)),
  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    },
  },
  user: {
    validateUserInfo: ({ user }) => {
      if (isOwnerEmail(typeof user.email === "string" ? user.email : null)) {
        return;
      }
      return {
        error: "unauthorized_email",
        errorDescription: UNAUTHORIZED_EMAIL_MESSAGE,
      };
    },
  },
  session: {
    cookieCache: {
      enabled: true,
      maxAge: 5 * 60,
    },
  },
  databaseHooks: {
    user: {
      create: {
        before: async (user) => {
          rejectUnauthorizedEmail(user.email);
        },
      },
    },
  },
  advanced: {
    trustedProxyHeaders: true,
  },
  onAPIError: {
    errorURL: "/login",
  },
  plugins: [
    jwt({
      jwks: {
        keyPairConfig: { alg: "RS256" },
      },
      jwt: {
        issuer: process.env.BETTER_AUTH_URL,
        audience: process.env.NEXT_PUBLIC_API_URL || "scenecraft-api",
        expirationTime: "15m",
        definePayload: ({ user }) => ({
          id: user.id,
          email: user.email,
        }),
      },
    }),
    nextCookies(),
  ],
});
