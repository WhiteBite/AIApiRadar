import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Sidebar } from "@/components/layout/sidebar";

export const metadata: Metadata = {
  title: "AiApiRadar",
  description: "Monitor free AI API credit offers",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark h-full">
      <body className="h-full antialiased">
        <Providers>
          <div className="flex h-screen overflow-hidden bg-zinc-950">
            <Sidebar />
            <main className="flex-1 min-h-0 overflow-hidden">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
