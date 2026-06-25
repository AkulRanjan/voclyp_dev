"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { VoClypLogo } from "@/components/VoClypLogo";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/#product", label: "Product" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/about", label: "About" },
];

export function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <header
        className={`fixed inset-x-0 top-0 z-50 transition-colors duration-200 ${
          scrolled
            ? "border-b border-border bg-background/80 backdrop-blur-md"
            : "border-b border-transparent"
        }`}
      >
        <nav className="site-container flex h-[52px] items-center justify-between">
          <Link href="/" className="flex items-center" aria-label="VoClyp home">
            <VoClypLogo height={34} showName />
          </Link>

          <ul className="hidden items-center gap-7 md:flex">
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link
                  href={l.href}
                  className="text-body-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-3">
            <Link
              href="/#book"
              className="btn-primary text-caption hidden rounded-full px-4 py-1.5 md:inline-flex"
            >
              Book a demo
            </Link>
            <button
              onClick={() => setOpen((v) => !v)}
              className="grid h-9 w-9 place-items-center md:hidden"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
            >
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </nav>
      </header>

      {open && (
        <div className="fixed inset-x-0 top-[52px] z-40 border-b border-border bg-background px-6 pb-5 pt-3 md:hidden">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="text-body-sm block border-b border-border py-3 font-medium text-muted-foreground"
            >
              {l.label}
            </Link>
          ))}
          <Link
            href="/#book"
            onClick={() => setOpen(false)}
            className="btn-primary text-body-sm mt-3 block rounded-full py-2.5 text-center"
          >
            Book a demo
          </Link>
        </div>
      )}
    </>
  );
}
