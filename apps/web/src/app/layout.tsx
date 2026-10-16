import React from "react";
import "./globals.css";
import { AuthProvider } from "../lib/auth-context";

export const metadata = {
  title: "StoreOps AI: retail promotions, verified",
  description:
    "StoreOps finds why a promotion is failing in a store, helps the rep fix it, and verifies the fix from shelf photos.",
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
