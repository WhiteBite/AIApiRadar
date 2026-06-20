interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  return (
    <div className="flex items-baseline gap-3 px-6 py-5 border-b border-zinc-800">
      <h1 className="text-xl font-semibold text-zinc-100">{title}</h1>
      {subtitle && <span className="text-sm text-zinc-500">{subtitle}</span>}
    </div>
  );
}
