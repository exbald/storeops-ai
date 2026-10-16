"use client";

import React, { useId, useState } from "react";
import { Button } from "../ui/button";
import { loadSampleAgreement, validateAgreementFile } from "./agreement-upload";

export interface AgreementFilePickerProps {
  label?: string;
  selectedName?: string | null;
  disabled?: boolean;
  onSelect: (file: File) => void;
  onError?: (message: string) => void;
}

/** PDF file input with a "Use sample agreement" shortcut. Validates before handing the file on. */
export function AgreementFilePicker({
  label = "Agreement PDF",
  selectedName,
  disabled = false,
  onSelect,
  onError,
}: AgreementFilePickerProps) {
  const inputId = useId();
  const [isLoadingSample, setIsLoadingSample] = useState(false);

  const accept = (file: File) => {
    const invalid = validateAgreementFile(file);
    if (invalid) {
      onError?.(invalid);
      return;
    }
    onSelect(file);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) accept(file);
    e.target.value = "";
  };

  const handleSample = async () => {
    setIsLoadingSample(true);
    try {
      accept(await loadSampleAgreement());
    } catch (err: unknown) {
      onError?.(err instanceof Error ? err.message : "Could not load the sample agreement.");
    } finally {
      setIsLoadingSample(false);
    }
  };

  return (
    <div className="space-y-1">
      <label htmlFor={inputId} className="block text-sm font-medium text-gray-700">
        {label}
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <input
          id={inputId}
          type="file"
          accept="application/pdf,.pdf"
          disabled={disabled}
          onChange={handleChange}
          className="text-sm text-gray-700 file:mr-3 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-gray-200"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleSample}
          isLoading={isLoadingSample}
          disabled={disabled}
        >
          Use sample agreement
        </Button>
      </div>
      {selectedName && (
        <p className="text-xs text-gray-600" data-testid="agreement-selected">
          Selected: <span className="font-medium">{selectedName}</span>
        </p>
      )}
    </div>
  );
}
