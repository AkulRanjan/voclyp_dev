import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "../../components/Button";
import { Icon } from "../../components/Icon";
import { usePitches } from "../../data/usePitches";
import { distinct } from "../../data/seed";
import type { PitchRow, SortDir, SortKey } from "../../data/types";
import { FilterBar, EMPTY_FILTERS, type Filters } from "./FilterBar";
import { PitchTable } from "./PitchTable";
import { PitchDrawer } from "./PitchDrawer";
import "./pitches.css";

function applyFilters(rows: PitchRow[], f: Filters): PitchRow[] {
  return rows.filter((r) => {
    if (f.brand && r.brand !== f.brand) return false;
    if (f.script && r.script !== f.script) return false;
    if (f.worker && r.worker !== f.worker) return false;
    if (f.status === "sale" && !r.sale) return false;
    if (f.status === "nosale" && r.sale) return false;
    if (f.status === "qualified" && r.pitchesQualified === 0) return false;
    if (f.status === "notqualified" && r.pitchesQualified > 0) return false;
    const day = r.date.slice(0, 10);
    if (f.startDate && day < f.startDate) return false;
    if (f.endDate && day > f.endDate) return false;
    return true;
  });
}

function sortRows(rows: PitchRow[], key: SortKey, dir: SortDir): PitchRow[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (key === "brand") return sign * a.brand.localeCompare(b.brand);
    return sign * (new Date(a.date).getTime() - new Date(b.date).getTime());
  });
}

export function PitchesPage() {
  const { rows, loading, error, refresh } = usePitches();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [params, setParams] = useSearchParams();

  const openId = params.get("instance");

  const brands = useMemo(() => distinct(rows, (r) => r.brand), [rows]);
  const scripts = useMemo(() => distinct(rows, (r) => r.script), [rows]);
  const workers = useMemo(() => distinct(rows, (r) => r.worker), [rows]);

  const visible = useMemo(
    () => sortRows(applyFilters(rows, filters), sortKey, sortDir),
    [rows, filters, sortKey, sortDir],
  );

  const openRow = openId ? rows.find((r) => r.id === openId) ?? null : null;

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "date" ? "desc" : "asc");
    }
  }

  function open(rowId: string) {
    const next = new URLSearchParams(params);
    next.set("instance", rowId);
    setParams(next, { replace: false });
  }

  function close() {
    const next = new URLSearchParams(params);
    next.delete("instance");
    setParams(next, { replace: false });
  }

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Pitches</h1>
          <p className="page__subtitle">
            {loading
              ? "Loading…"
              : `${visible.length} of ${rows.length} pitch record${rows.length === 1 ? "" : "s"}`}
          </p>
        </div>
        <Button variant="outline" onClick={() => void refresh()}>
          <Icon name="refresh" size={16} />
          Refresh
        </Button>
      </div>

      <FilterBar
        filters={filters}
        onChange={setFilters}
        brands={brands}
        scripts={scripts}
        workers={workers}
      />

      {error && (
        <div className="pitches-error">
          {error} — check the API key and data source in Settings.
        </div>
      )}

      <PitchTable
        rows={visible}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={toggleSort}
        onOpen={open}
        openId={openId}
      />

      <PitchDrawer row={openRow} onClose={close} />
    </div>
  );
}
