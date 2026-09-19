import type { ReactNode } from "react";
import { Hanken_Grotesk, Young_Serif } from "next/font/google";

import "./globals.css";

const hanken = Hanken_Grotesk({
  subsets: ["latin"],
  variable: "--font-hanken",
  display: "swap",
});

const youngSerif = Young_Serif({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-young-serif",
  display: "swap",
});

export const metadata = {
  title: "Send your details",
  description:
    "Share your name, email and resume, and an attorney will reach out to you.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${hanken.variable} ${youngSerif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
