import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Jagon Space Station — 台股偵測中樞",
  description: "整合漲停、籌碼、處置預警與公告偵測的台股盤面觀測站",
  // 不公開的網站：只給知道網址的人看，不讓搜尋引擎收錄
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-TW" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
