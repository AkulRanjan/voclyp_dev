export function SectionHeader({
  eyebrow,
  title,
  highlight,
  align = "center",
}: {
  eyebrow: string;
  title: string;
  highlight?: string;
  align?: "center" | "left";
}) {
  return (
    <div
      className={`mb-10 max-w-3xl ${align === "center" ? "mx-auto text-center" : ""}`}
    >
      <span className="eyebrow">{eyebrow}</span>
      <h2 className="text-title mt-3">
        {title}
        {highlight && (
          <>
            {" "}
            <span className="text-bold-point">{highlight}</span>
          </>
        )}
      </h2>
    </div>
  );
}
