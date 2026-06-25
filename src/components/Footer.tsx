import Link from "next/link";
import { VoClypLogo } from "@/components/VoClypLogo";

const COLS = [
  {
    title: "Product",
    links: [
      { label: "Live demo", href: "/#demo" },
      { label: "Field capture", href: "/#product" },
      { label: "How it works", href: "/how-it-works" },
      { label: "Privacy", href: "/#privacy" },
      { label: "Pricing", href: "/pricing" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Home", href: "/" },
      { label: "About", href: "/about" },
      { label: "Book a demo", href: "/#book" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Privacy Policy", href: "/#privacy" },
      { label: "Terms", href: "/#privacy" },
      { label: "Recording Notice", href: "/#privacy" },
    ],
  },
  {
    title: "Connect",
    links: [
      { label: "support@voclyp.com", href: "mailto:support@voclyp.com", external: true },
    ],
  },
];

export function Footer() {
  return (
    <footer className="border-t border-border py-14">
      <div className="site-container">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
          <div>
            <Link href="/" className="mb-3 inline-block" aria-label="VoClyp home">
              <VoClypLogo height={34} showName />
            </Link>
            <p className="text-body-sm max-w-xs text-muted-foreground">
              Every field conversation, turned into market intelligence. Every
              signal, put to work.
            </p>
          </div>

          {COLS.map((col) => (
            <div key={col.title}>
              <h4 className="eyebrow mb-3">{col.title}</h4>
              {col.links.map((l) =>
                "external" in l && l.external ? (
                  <a
                    key={l.label}
                    href={l.href}
                    className="text-body-sm block py-1 text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {l.label}
                  </a>
                ) : (
                  <Link
                    key={l.label}
                    href={l.href}
                    className="text-body-sm block py-1 text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {l.label}
                  </Link>
                ),
              )}
            </div>
          ))}
        </div>

        <div className="mt-12 border-t border-border pt-6 text-center">
          <p className="text-caption font-medium text-amber">
            Made in India. Stored in India.
          </p>
        </div>
      </div>
    </footer>
  );
}
