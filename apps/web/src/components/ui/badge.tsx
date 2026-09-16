import React from "react";

export type BadgeVariant = "success" | "warning" | "danger" | "neutral" | "info";

export interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
  labelPrefix?: string;
}

export function Badge({
  children,
  variant = "neutral",
  className = "",
  labelPrefix,
}: BadgeProps) {
  const styles: Record<BadgeVariant, string> = {
    success: "bg-green-100 text-green-800 border-green-200",
    warning: "bg-amber-100 text-amber-800 border-amber-200",
    danger: "bg-red-100 text-red-800 border-red-200",
    neutral: "bg-gray-100 text-gray-800 border-gray-200",
    info: "bg-blue-100 text-blue-800 border-blue-200",
  };

  const statusDescriptions: Record<BadgeVariant, string> = {
    success: "Status: Success -",
    warning: "Status: Warning -",
    danger: "Status: Alert -",
    neutral: "Status: Information -",
    info: "Status: Info -",
  };

  const prefix = labelPrefix || statusDescriptions[variant];

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[variant]} ${className}`}
    >
      <span className="sr-only">{prefix} </span>
      {children}
    </span>
  );
}
