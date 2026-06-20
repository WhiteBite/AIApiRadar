import { cn } from "@/lib/utils";

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        "h-8 rounded-md border border-zinc-700 bg-zinc-800/80 px-3 text-sm text-zinc-100",
        "placeholder:text-zinc-500",
        "focus:outline-none focus:border-zinc-500",
        "transition-colors",
        className
      )}
      {...props}
    />
  );
}
