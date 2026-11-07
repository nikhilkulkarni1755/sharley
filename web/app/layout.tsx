import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sharley board",
  description: "An independent verifier for AI-written code: sealed hidden tests decide the verdict.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
