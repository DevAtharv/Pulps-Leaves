import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pulps & Leaves — Direct from Farm, India",
  description:
    "Authentic Assam tea, Bihar's finest makhana, and seasonal Malda mangoes — sourced directly from farms across India. Pure. Regional. No chemicals.",
  keywords: "makhana, Assam tea, Malda mangoes, farm fresh, Bihar, organic India",
  openGraph: {
    title: "Pulps & Leaves — Direct from Farm, India",
    description:
      "Authentic Assam tea, Bihar's finest makhana, and seasonal Malda mangoes — sourced directly from farms.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
