import { Dropdown, type Option } from "../../components/Dropdown";
import { Icon } from "../../components/Icon";

export interface Filters {
  brand: string;
  script: string;
  worker: string;
  status: string; // "" = All
  startDate: string; // yyyy-mm-dd
  endDate: string;
}

export const EMPTY_FILTERS: Filters = {
  brand: "",
  script: "",
  worker: "",
  status: "",
  startDate: "",
  endDate: "",
};

const STATUS_OPTIONS: Option[] = [
  { value: "sale", label: "Sale made" },
  { value: "nosale", label: "No sale" },
  { value: "qualified", label: "Has qualified" },
  { value: "notqualified", label: "None qualified" },
];

function toOptions(values: string[]): Option[] {
  return values.map((v) => ({ value: v, label: v }));
}

export function FilterBar({
  filters,
  onChange,
  brands,
  scripts,
  workers,
}: {
  filters: Filters;
  onChange: (next: Filters) => void;
  brands: string[];
  scripts: string[];
  workers: string[];
}) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });

  return (
    <div className="filterbar">
      <Dropdown
        value={filters.brand}
        onChange={(brand) => set({ brand })}
        options={toOptions(brands)}
        placeholder="Brand"
      />
      <Dropdown
        value={filters.script}
        onChange={(script) => set({ script })}
        options={toOptions(scripts)}
        placeholder="Script"
      />
      <Dropdown
        value={filters.worker}
        onChange={(worker) => set({ worker })}
        options={toOptions(workers)}
        placeholder="Worker"
      />
      <Dropdown
        value={filters.status}
        onChange={(status) => set({ status })}
        options={STATUS_OPTIONS}
        placeholder="All"
      />

      <div className="filter-date">
        <input
          type="date"
          aria-label="Start date"
          value={filters.startDate}
          onChange={(e) => set({ startDate: e.target.value })}
        />
        <Icon name="calendar" size={15} className="filter-date__icon" />
      </div>
      <div className="filter-date">
        <input
          type="date"
          aria-label="End date"
          value={filters.endDate}
          onChange={(e) => set({ endDate: e.target.value })}
        />
        <Icon name="calendar" size={15} className="filter-date__icon" />
      </div>
    </div>
  );
}
