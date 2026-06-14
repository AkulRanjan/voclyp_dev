// Lightweight stand-in for shell routes that aren't part of this build. The
// spec asks to build only the Pitches section but keep the shell holistic.
export function Placeholder({ title }: { title: string }) {
  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">{title}</h1>
          <p className="page__subtitle">Part of the VoClyp manager console</p>
        </div>
      </div>
      <div className="placeholder">
        <h3>{title}</h3>
        <p>This section of the console is not part of the current build.</p>
      </div>
    </div>
  );
}
