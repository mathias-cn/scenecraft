export const NAV_ITEMS = [
  { href: "/projects", label: "Projetos" },
  { href: "/characters", label: "Personagens" },
  { href: "/styles", label: "Estilos" },
  { href: "/settings", label: "Configurações" },
] as const;

export type NavHref = (typeof NAV_ITEMS)[number]["href"];

export function titleForPath(pathname: string): string {
  if (pathname === "/projects/new") return "Novo projeto";
  if (pathname.startsWith("/projects/") && pathname !== "/projects") return "Projeto";
  if (pathname === "/characters/new") return "Novo personagem";
  if (pathname.startsWith("/characters/") && pathname !== "/characters") return "Personagem";
  const match = NAV_ITEMS.find(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
  return match?.label ?? "SceneCraft";
}
