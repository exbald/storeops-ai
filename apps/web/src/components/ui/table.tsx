import React from "react";

export interface Column<T> {
  key: string;
  header: string;
  render?: (item: T) => React.ReactNode;
  className?: string;
}

export interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (item: T) => string;
  emptyMessage?: string;
  caption?: string;
}

export function Table<T>({
  columns,
  data,
  keyExtractor,
  emptyMessage = "No records found",
  caption,
}: TableProps<T>) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-left text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-gray-50 text-xs font-semibold uppercase tracking-wider text-gray-500">
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col" className={`px-6 py-3 ${col.className || ""}`}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-6 py-8 text-center text-gray-500">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((item) => (
              <tr key={keyExtractor(item)} className="hover:bg-gray-50 transition-colors">
                {columns.map((col) => (
                  <td key={col.key} className={`px-6 py-4 whitespace-nowrap text-gray-900 ${col.className || ""}`}>
                    {col.render ? col.render(item) : (item as Record<string, unknown>)[col.key] as React.ReactNode}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
