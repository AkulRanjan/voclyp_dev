import { Badge } from "../../components/Badge";
import { Icon } from "../../components/Icon";
import { intentTone } from "../../lib/bands";
import { formatShortDate } from "../../lib/format";
import type { PitchRow, SortDir, SortKey } from "../../data/types";

function SortHeader({
  label,
  col,
  sortKey,
  sortDir,
  onSort,
}: {
  label: string;
  col: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
}) {
  const active = sortKey === col;
  return (
    <th className="pt-th pt-th--sortable" onClick={() => onSort(col)}>
      <span className="pt-th__inner">
        {label}
        <Icon
          name={active ? (sortDir === "asc" ? "arrow-up" : "arrow-down") : "sort"}
          size={13}
          className={`pt-sort${active ? " pt-sort--active" : ""}`}
        />
      </span>
    </th>
  );
}

export function PitchTable({
  rows,
  sortKey,
  sortDir,
  onSort,
  onOpen,
  openId,
}: {
  rows: PitchRow[];
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (key: SortKey) => void;
  onOpen: (rowId: string) => void;
  openId: string | null;
}) {
  return (
    <div className="pt-wrap">
      <table className="pt">
        <thead>
          <tr>
            <th className="pt-th pt-th--exp" />
            <SortHeader label="BRAND" col="brand" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
            <th className="pt-th">SCRIPT</th>
            <th className="pt-th">STORE</th>
            <th className="pt-th">WORKER</th>
            <th className="pt-th pt-th--num">BEST</th>
            <th className="pt-th pt-th--num">AVG</th>
            <th className="pt-th">PITCHES</th>
            <th className="pt-th">SALE</th>
            <th className="pt-th">INTENT</th>
            <SortHeader label="DATE" col="date" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const open = r.id === openId;
            return (
              <tr
                key={r.id}
                className={`pt-row${open ? " pt-row--open" : ""}`}
                onClick={() => onOpen(r.id)}
              >
                <td className="pt-td pt-td--exp">
                  <button
                    className="pt-exp"
                    aria-label={open ? "Close details" : "Open details"}
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpen(r.id);
                    }}
                  >
                    <Icon name={open ? "minus" : "plus"} size={15} />
                  </button>
                </td>
                <td className="pt-td">
                  <div className="pt-primary">{r.brand}</div>
                  <div className="pt-sub">{r.brandSubtitle}</div>
                </td>
                <td className="pt-td">
                  <div className="pt-primary">{r.script}</div>
                  <div className="pt-sub">Coverage {r.coverage}%</div>
                </td>
                <td className="pt-td">{r.store}</td>
                <td className="pt-td pt-td--worker">{r.worker}</td>
                <td className="pt-td pt-td--num">{r.best}</td>
                <td className="pt-td pt-td--num">{r.avg}</td>
                <td className="pt-td">
                  <div className="pt-primary">{r.pitchesTotal} total</div>
                  <div className="pt-sub">{r.pitchesQualified} qualified</div>
                </td>
                <td className="pt-td">{r.sale ? "Yes" : "No"}</td>
                <td className="pt-td">
                  <Badge tone={intentTone(r.intent)}>{r.intent}</Badge>
                </td>
                <td className="pt-td pt-td--date">{formatShortDate(r.date)}</td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td className="pt-empty" colSpan={11}>
                No pitches match these filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
