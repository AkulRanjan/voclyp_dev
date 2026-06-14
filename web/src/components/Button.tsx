import type { ButtonHTMLAttributes } from "react";
import "./button.css";

type Variant = "primary" | "outline" | "ghost";

export function Button({
  variant = "outline",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={`btn btn--${variant} ${className}`} {...rest} />;
}
