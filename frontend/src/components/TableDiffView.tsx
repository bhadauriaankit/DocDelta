import type { SpreadsheetDiff, TableDiff, TableRowDiff } from "@/lib/api";

const ROW_BADGE_STYLE: Record<string, string> = {
  added: "bg-mark-add-bg text-mark-add",
  removed: "bg-mark-remove-bg text-mark-remove",
  modified: "bg-mark-replace-bg text-mark-replace",
};

function RowBadge({ type }: { type: string }) {
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${ROW_BADGE_STYLE[type] ?? ""}`}>
      {type}
    </span>
  );
}

function ModifiedRowCells({ row }: { row: TableRowDiff }) {
  const original = row.original ?? [];
  const modified = row.modified ?? [];
  const width = Math.max(original.length, modified.length);

  return (
    <span className="flex flex-wrap gap-x-1 gap-y-0.5">
      {Array.from({ length: width }, (_, col) => {
        const changed = row.cell_changes.some((c) => c.col === col);
        const oCell = original[col] ?? "";
        const mCell = modified[col] ?? "";
        return (
          <span key={col} className="whitespace-pre">
            {changed ? (
              <>
                <span className="bg-mark-remove-bg text-mark-remove line-through">{oCell}</span>
                <span className="text-muted"> → </span>
                <span className="bg-mark-add-bg text-mark-add">{mCell}</span>
              </>
            ) : (
              <span className="text-ink/70">{oCell}</span>
            )}
            {col < width - 1 && <span className="text-muted"> | </span>}
          </span>
        );
      })}
    </span>
  );
}

function TableCard({ table }: { table: TableDiff }) {
  const changedRows = table.rows.filter((r) => r.type !== "equal");

  return (
    <div className="rounded-sm border border-paper-line bg-white p-6">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h3 className="font-serif text-lg text-ink">{table.name}</h3>
        <div className="flex gap-3 text-xs text-muted">
          <span className="text-mark-add">{table.stats.added ?? 0} added</span>
          <span className="text-mark-remove">{table.stats.removed ?? 0} removed</span>
          <span className="text-mark-replace">{table.stats.modified ?? 0} modified</span>
        </div>
      </div>

      {changedRows.length === 0 ? (
        <p className="text-sm text-muted">No row changes in this sheet.</p>
      ) : (
        <div className="flex flex-col divide-y divide-paper-line font-mono text-sm">
          {changedRows.map((row, i) => (
            <div key={i} className="flex items-start gap-3 py-2">
              <RowBadge type={row.type} />
              {row.type === "modified" ? (
                <ModifiedRowCells row={row} />
              ) : (
                <span className={row.type === "removed" ? "text-mark-remove line-through" : "text-mark-add"}>
                  {(row.original ?? row.modified ?? []).join(" | ")}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TableDiffView({ diff }: { diff: SpreadsheetDiff }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="text-xs uppercase tracking-[0.15em] text-muted">Table changes</div>

      {(diff.added_tables.length > 0 || diff.removed_tables.length > 0) && (
        <div className="rounded-sm border border-paper-line bg-white px-4 py-3 text-sm">
          {diff.added_tables.length > 0 && (
            <p className="text-mark-add">+ Added sheet{diff.added_tables.length > 1 ? "s" : ""}: {diff.added_tables.join(", ")}</p>
          )}
          {diff.removed_tables.length > 0 && (
            <p className="text-mark-remove">− Removed sheet{diff.removed_tables.length > 1 ? "s" : ""}: {diff.removed_tables.join(", ")}</p>
          )}
        </div>
      )}

      <div className="flex flex-col gap-6">
        {diff.tables.map((table) => (
          <TableCard key={table.name} table={table} />
        ))}
      </div>
    </div>
  );
}
