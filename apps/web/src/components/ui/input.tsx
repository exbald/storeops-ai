"use client";

import React, { useId } from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export function Input({
  label,
  error,
  helperText,
  id,
  className = "",
  disabled,
  required,
  ...props
}: InputProps) {
  const generatedId = useId();
  const inputId = id || generatedId;
  const errorId = `${inputId}-error`;
  const helperId = `${inputId}-helper`;

  return (
    <div className="w-full flex flex-col gap-1 text-left">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-gray-700">
          {label}
          {required && <span className="text-red-500 ml-1" aria-hidden="true">*</span>}
        </label>
      )}
      <input
        id={inputId}
        disabled={disabled}
        required={required}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : helperText ? helperId : undefined}
        className={`block w-full px-3 py-2 border rounded-md shadow-sm sm:text-sm focus:outline-none focus:ring-2 focus:ring-offset-1 transition-colors ${
          error
            ? "border-red-300 text-red-900 placeholder-red-300 focus:ring-red-500 focus:border-red-500"
            : "border-gray-300 focus:ring-blue-500 focus:border-blue-500"
        } ${disabled ? "bg-gray-100 cursor-not-allowed" : "bg-white"} ${className}`}
        {...props}
      />
      {error && (
        <p id={errorId} className="text-sm text-red-600 flex items-center gap-1" role="alert">
          <span className="sr-only">Error:</span>
          <span>{error}</span>
        </p>
      )}
      {!error && helperText && (
        <p id={helperId} className="text-xs text-gray-500">
          {helperText}
        </p>
      )}
    </div>
  );
}
