import Link from "next/link";
import type { ComponentPropsWithoutRef } from "react";

type BtnProps = ComponentPropsWithoutRef<typeof Link> & {
  variant?: "primary" | "secondary" | "amber";
};

const variants = {
  primary: "btn-primary",
  secondary: "liquid-glass text-foreground",
  amber: "bg-amber text-[#1a1205] hover:opacity-90",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  href,
  ...props
}: BtnProps) {
  return (
    <Link
      href={href}
      className={`text-body-sm inline-flex items-center justify-center rounded-full px-6 py-2.5 font-medium ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </Link>
  );
}
