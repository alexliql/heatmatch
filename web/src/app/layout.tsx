import type { Metadata } from "next";

import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "heatmatch — waste heat reuse in New York State",
  description:
    "Ranks New York State data centers by how well their waste heat could be reused by nearby heat consumers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
