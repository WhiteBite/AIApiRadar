import { cn } from "@/lib/utils";

interface CardProps {
  className?: string;
  children: React.ReactNode;
  hover?: boolean;
  onClick?: () => void;
}

export function Card({ className, children, hover, onClick }: CardProps) {
  return (
    <div
      className={cn(
        "bg-zinc-900 border border-zinc-800 rounded-xl p-4",
        hover && "hover:bg-zinc-800/50 transition-colors cursor-pointer",
        className
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}
