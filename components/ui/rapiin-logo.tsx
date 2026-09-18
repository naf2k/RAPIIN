import { cn } from "@/lib/utils";

export function RapiinLogo({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("relative inline-block h-[22px] w-[22px] flex-shrink-0 rotate-[-12deg]", className)}
    >
      <span className="absolute left-0.5 top-0 block h-[18px] w-[9px] rounded-[5px] border-2 border-current" />
      <span className="absolute bottom-0 right-0.5 block h-[18px] w-[9px] rounded-[5px] border-2 border-current opacity-[0.58]" />
    </span>
  );
}
