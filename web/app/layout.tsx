import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoSeguro — agente de cotação",
  description: "Chat com o agente e painel de trace da execução",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
