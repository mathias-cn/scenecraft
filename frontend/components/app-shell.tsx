"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";

import { IconCharacters, IconClose, IconCosts, IconMenu, IconProjects, IconSettings, IconStyles } from "@/components/icons";
import { NAV_ITEMS, titleForPath } from "@/lib/nav";

const ICONS = {
  "/projects": IconProjects,
  "/costs": IconCosts,
  "/characters": IconCharacters,
  "/styles": IconStyles,
  "/settings": IconSettings,
} as const;

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const title = titleForPath(pathname);

  return (
    <div className="flex min-h-screen bg-ink-950 text-zinc-100">
      {open ? (
        <button
          type="button"
          aria-label="Fechar menu"
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setOpen(false)}
        />
      ) : null}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-white/[0.06] bg-ink-900 transition-transform lg:static lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center justify-between gap-2 border-b border-white/[0.06] px-4">
          <Link href="/projects" className="min-w-0" onClick={() => setOpen(false)}>
            <span className="font-mono text-[11px] tracking-[0.22em] text-brass-500 uppercase">
              SceneCraft
            </span>
            <span className="mt-0.5 block font-mono text-[10px] tracking-widest text-white/30">
              pipeline
            </span>
          </Link>
          <button
            type="button"
            className="rounded-md p-1 text-white/50 hover:bg-white/5 lg:hidden"
            onClick={() => setOpen(false)}
            aria-label="Fechar sidebar"
          >
            <IconClose className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex flex-1 flex-col gap-1 p-3">
          <p className="mb-2 px-2 font-mono text-[10px] tracking-[0.18em] text-white/25 uppercase">
            Navegação
          </p>
          {NAV_ITEMS.map((item) => {
            const Icon = ICONS[item.href];
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition ${
                  active
                    ? "bg-white/[0.06] text-brass-400"
                    : "text-white/55 hover:bg-white/[0.04] hover:text-white/85"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-white/[0.06] bg-ink-950/90 px-4 backdrop-blur lg:px-6">
          <button
            type="button"
            className="rounded-md p-1.5 text-white/60 hover:bg-white/5 lg:hidden"
            onClick={() => setOpen(true)}
            aria-label="Abrir menu"
          >
            <IconMenu className="h-5 w-5" />
          </button>
          <h1 className="text-sm font-medium tracking-tight text-white/90">{title}</h1>
          <span className="ml-auto hidden font-mono text-[10px] tracking-widest text-white/25 uppercase sm:inline">
            YouTube · auto
          </span>
        </header>
        <main className="min-w-0 flex-1 px-4 py-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
