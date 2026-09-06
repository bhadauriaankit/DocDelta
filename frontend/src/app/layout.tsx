import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DocCompare AI",
  description: "Upload two documents. See exactly what changed.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-paper text-ink">{children}</body>
    </html>
  );
}
