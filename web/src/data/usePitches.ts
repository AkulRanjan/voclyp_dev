import { useCallback, useEffect, useState } from "react";
import type { PitchRow } from "./types";
import { getDataSource, loadPitches } from "./source";

// Loads pitch rows from the active data source (seed or live VoClyp). Returns a
// refresh() the Refresh button can call.
export function usePitches() {
  const [rows, setRows] = useState<PitchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await loadPitches(getDataSource()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { rows, loading, error, refresh };
}
