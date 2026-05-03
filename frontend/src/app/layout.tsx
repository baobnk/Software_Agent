import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BnK DeepAgent",
  description: "Multi-agent BRD + WBS document generation",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className="dark">
      <body className="min-h-screen bg-[var(--background)] text-[var(--foreground)] antialiased">
        {children}
      </body>
    </html>
  );
}
