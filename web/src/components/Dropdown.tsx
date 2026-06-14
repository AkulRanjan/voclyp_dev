import { Icon } from "./Icon";
import "./dropdown.css";

export interface Option {
  value: string;
  label: string;
}

// A native <select> styled to match the filter bar: light border, rounded,
// gray placeholder text when nothing is chosen, custom chevron. Native keeps
// keyboard/a11y behavior for free.
export function Dropdown({
  value,
  onChange,
  options,
  placeholder,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  placeholder: string;
  ariaLabel?: string;
}) {
  const isPlaceholder = value === "";
  return (
    <div className="dropdown">
      <select
        className={`dropdown__select${isPlaceholder ? " dropdown__select--placeholder" : ""}`}
        value={value}
        aria-label={ariaLabel || placeholder}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <Icon name="chevron-down" size={16} className="dropdown__chevron" />
    </div>
  );
}
