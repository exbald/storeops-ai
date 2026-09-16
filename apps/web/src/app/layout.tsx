import React from "react";
import "./globals.css";
import { AuthProvider } from "../lib/auth-context";

export const metadata = {
  title: "StoreOps - Autonomous Retail Operations Intelligence",
  description: "Autonomous retail operations intelligence platform with multimodal vision verification.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
