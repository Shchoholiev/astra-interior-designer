import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Astra Interior Designer",
  description: "Design and explore interactive 3D interiors through conversation.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
