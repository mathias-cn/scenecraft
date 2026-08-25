export const NAV_ITEMS = [
  { href: "/projects", label: "Projetos" },
  { href: "/settings", label: "Configurações" },
] as const;

export type NavHref = (typeof NAV_ITEMS)[number]["href"];

export function titleForPath(pathname: string): string {
  const match = NAV_ITEMS.find(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
  return match?.label ?? "SceneCraft";
}
