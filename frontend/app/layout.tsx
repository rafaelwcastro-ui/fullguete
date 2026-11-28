import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
export const metadata: Metadata = { title: "Fullguete | Prévia de design", description: "Prévia isolada da nova interface comercial" };
export default function RootLayout({children}: {children: ReactNode}) {
 return <html lang="pt-BR"><body>{children}</body></html>;
}
