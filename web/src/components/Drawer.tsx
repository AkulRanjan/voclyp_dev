import { useEffect } from "react";
import { Icon } from "./Icon";
import "./drawer.css";

// Right-side slide-over over a dimmed backdrop. Closes on ✕, backdrop click,
// or Esc; locks body scroll while open. The content underneath stays mounted.
export function Drawer({
  open,
  onClose,
  title,
  children,
  width = 560,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="drawer-root" role="dialog" aria-modal="true">
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer-panel" style={{ width }}>
        <header className="drawer-head">
          <h2 className="drawer-title">{title}</h2>
          <button className="drawer-close" onClick={onClose} aria-label="Close">
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}
