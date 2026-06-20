import { cn } from "@/lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost";
  size?: "sm" | "md";
}

export function Button({
  variant = "default",
  size = "md",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors",
        "focus-visible:outline-none disabled:opacity-50 disabled:cursor-not-allowed",
        size === "sm" && "h-7 px-2.5 text-xs",
        size === "md" && "h-8 px-3 text-sm",
        variant === "default" && "bg-zinc-100 text-zinc-900 hover:bg-zinc-200",
        variant === "outline" &&
        "border border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100",
        variant === "ghost" &&
        "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100",
        className
      )}
      {...props}
    />
  );
}
