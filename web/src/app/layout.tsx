import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "heatmatch",
  description: "Ranking New York State data centers by waste-heat reuse potential.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
