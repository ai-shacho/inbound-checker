import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "インバウンド企業判定システム",
  description: "企業HPのURLからインバウンド企業かどうかを判定するシステム",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body className="bg-white text-gray-900 antialiased">{children}</body>
    </html>
  );
}
