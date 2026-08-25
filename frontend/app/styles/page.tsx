import type { Metadata } from "next";

import { StylesAdmin } from "@/components/styles-admin";

export const metadata: Metadata = {
  title: "Estilos",
};

export default function StylesPage() {
  return <StylesAdmin />;
}
