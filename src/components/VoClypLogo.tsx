import Image from "next/image";

type VoClypLogoProps = {
  className?: string;
  height?: number;
  /** Show the VoClyp wordmark text beside the logo mark */
  showName?: boolean;
};

export function VoClypLogo({
  className = "",
  height = 28,
  showName = false,
}: VoClypLogoProps) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      <Image
        src="/logo.svg"
        alt="VoClyp"
        width={height}
        height={height}
        className="shrink-0"
        style={{ height, width: height }}
        priority
      />
      {showName && (
        <span className="text-[1.25rem] font-semibold tracking-[-0.02em]">
          VoClyp
        </span>
      )}
    </span>
  );
}
