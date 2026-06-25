import Link from "next/link";
import { ChevronRight } from "lucide-react";

export function PageBreadcrumb({ current }: { current: string }) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="site-container mb-6 flex items-center gap-1.5 text-caption text-muted-foreground"
    >
      <Link href="/" className="transition-colors hover:text-foreground">
        Home
      </Link>
      <ChevronRight size={14} className="opacity-40" aria-hidden />
      <span className="text-foreground/70">{current}</span>
    </nav>
  );
}
