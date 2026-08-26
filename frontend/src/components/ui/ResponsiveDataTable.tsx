import type { ReactNode } from 'react';

export interface DataColumn<T> {
  key: string;
  header?: ReactNode;
  render: (row: T) => ReactNode;
  headerClassName?: string;
  cellClassName?: string;
  align?: 'left' | 'right' | 'center';
  mobileLabel?: string;
  mobilePrimary?: boolean;
  mobileSecondary?: boolean;
  mobileHidden?: boolean;
  mobileFull?: boolean;
}

interface ResponsiveDataTableProps<T> {
  columns: DataColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  cardBadge?: (row: T) => ReactNode;
  cardActions?: (row: T) => ReactNode;
  onRowClick?: (row: T) => void;
  tableActions?: (row: T) => ReactNode;
  tableActionsHeader?: ReactNode;
  tableClassName?: string;
  darkHeader?: boolean;
  className?: string;
  empty?: ReactNode;
}

const alignClass = (align?: 'left' | 'right' | 'center') =>
  align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';

export default function ResponsiveDataTable<T>({
  columns,
  rows,
  rowKey,
  cardBadge,
  cardActions,
  onRowClick,
  tableActions,
  tableActionsHeader = 'Acciones',
  tableClassName = '',
  darkHeader = false,
  className = '',
  empty,
}: ResponsiveDataTableProps<T>) {
  const primary = columns.find((c) => c.mobilePrimary && !c.mobileHidden) ?? columns.find((c) => !c.mobileHidden);
  const secondary = columns.find((c) => c.mobileSecondary && !c.mobileHidden);
  const bodyCols = columns.filter(
    (c) => c.mobileLabel && !c.mobileHidden && c.key !== primary?.key && c.key !== secondary?.key
  );

  return (
    <div className={className}>
      {rows.length === 0 ? (
        empty ?? null
      ) : (
        <>
          {/* Desktop / tablet: tabla */}
          <div className={`hidden overflow-x-auto md:block ${tableClassName}`}>
            <table className="w-full border-collapse text-left">
              <thead>
                <tr>
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      className={
                        darkHeader
                          ? `px-5 py-4 border-b border-yeikar-secondary/20 font-headline uppercase text-xs tracking-wider bg-yeikar-neutral text-yeikar-tertiary ${alignClass(col.align)}`
                          : `table-th ${alignClass(col.align)} ${col.headerClassName ?? ''}`
                      }
                    >
                      {col.header}
                    </th>
                  ))}
                  {tableActions && (
                    <th
                      className={
                        darkHeader
                          ? 'px-5 py-4 border-b border-yeikar-secondary/20 font-headline uppercase text-xs tracking-wider bg-yeikar-neutral text-yeikar-tertiary text-right'
                          : `table-th text-right ${alignClass('right')}`
                      }
                    >
                      {tableActionsHeader}
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-yeikar-secondary-light/5">
                {rows.map((row) => (
                  <tr
                    key={rowKey(row)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={`transition-colors hover:bg-yeikar-tertiary/10 ${onRowClick ? 'cursor-pointer' : ''}`}
                  >
                    {columns.map((col) => (
                      <td key={col.key} className={`table-td ${alignClass(col.align)} ${col.cellClassName ?? ''}`}>
                        {col.render(row)}
                      </td>
                    ))}
                    {tableActions && (
                      <td className="table-td text-right">
                        <div className="flex items-center justify-end gap-2">{tableActions(row)}</div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Móvil: tarjetas */}
          <ul className="space-y-3 md:hidden">
            {rows.map((row) => (
              <li
                key={rowKey(row)}
                className={`card overflow-hidden ${onRowClick ? 'cursor-pointer' : ''}`}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                <div className="flex items-start justify-between gap-3 px-4 pb-3 pt-4">
                  <div className="min-w-0">
                    {primary && (
                      <div className="truncate font-headline font-bold text-yeikar-secondary">{primary.render(row)}</div>
                    )}
                    {secondary && (
                      <div className="mt-0.5 truncate text-xs text-yeikar-neutral/55">{secondary.render(row)}</div>
                    )}
                  </div>
                  {cardBadge && <div className="shrink-0">{cardBadge(row)}</div>}
                </div>

                {bodyCols.length > 0 && (
                  <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 px-4 pb-4">
                    {bodyCols.map((col) => (
                      <div key={col.key} className={`min-w-0 ${col.mobileFull ? 'col-span-2' : ''}`}>
                        <p className="font-mono text-[9px] uppercase tracking-wider text-yeikar-neutral/40">
                          {col.mobileLabel ?? col.header ?? col.key}
                        </p>
                        <div className="mt-0.5 break-words text-sm text-yeikar-neutral/90">{col.render(row)}</div>
                      </div>
                    ))}
                  </div>
                )}

                {cardActions && (
                  <div className="flex flex-wrap items-center gap-2 border-t border-yeikar-secondary-light/10 bg-yeikar-tertiary/40 px-4 py-3">
                    {cardActions(row)}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
