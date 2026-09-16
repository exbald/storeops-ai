"use client";

import React, { useId } from "react";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  options: SelectOption[];
  error?: string;
  helperText?: string;
}

export function Select({
  label,
  options,
  error,
  helperText,
  id,
  className = "",
  disabled,
  required,
  ...props
}: SelectProps) {
  const generatedId = useId();
  const selectId = id || generatedId;
  const errorId = `${selectId}-error`;
  const helperId = `${selectId}-helper`;

  return (
    <div className="w-full flex flex-col gap-1 text-left">
      <label htmlFor={selectId} className="block text-sm font-medium text-gray-700">
        {label}
        {required && <span className="text-red-500 ml-1" aria-hidden="true">*</span>}
      </label>
      <select
        id={selectId}
        disabled={disabled}
        required={required}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : helperText ? helperId : undefined}
        className={`block w-full px-3 py-2 border rounded-md shadow-sm sm:text-sm focus:outline-none focus:ring-2 focus:ring-offset-1 transition-colors ${
          error
            ? "border-red-300 text-red-900 focus:ring-red-500 focus:border-red-500"
            : "border-gray-300 focus:ring-blue-500 focus:border-blue-500"
        } ${disabled ? "bg-gray-100 cursor-not-allowed" : "bg-white"} ${className}`}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
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
