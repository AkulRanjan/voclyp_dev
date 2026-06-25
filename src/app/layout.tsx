import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";

const geist = Geist({
  variable: "--font-geist",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://voclyp.com"),
  title: "VoClyp",
  description:
    "VoClyp turns everyday field conversations into market insights for marketing and product teams. Privacy-first, with audio that auto-deletes. All stored in India.",
  openGraph: {
    title: "VoClyp",
    description:
      "Turn every field conversation into market intelligence. Privacy-first. Stored in India.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable}`}>
      <body>
        <span id="top" />
        <Nav />
        {children}
        <Footer />
      </body>
    </html>
  );
}
