import Link from "next/link";
import { Zap, BarChart3, Settings } from "lucide-react";
import { fetchStats } from "@/lib/api";
import { NavLink } from "./nav-link";

const SOURCES = [
  { key: "certstream", label: "CertStream", dot: "bg-cyan-400" },
  { key: "forum_rss", label: "Forums", dot: "bg-orange-400" },
  { key: "github", label: "GitHub", dot: "bg-zinc-400" },
  { key: "directories", label: "Directories", dot: "bg-lime-400" },
  { key: "producthunt", label: "ProductHunt", dot: "bg-red-400" },
  { key: "coupon", label: "Coupon", dot: "bg-purple-400" },
  { key: "telegram", label: "Telegram", dot: "bg-sky-400" },
] as const;

export async function Sidebar() {
  let stats: Awaited<ReturnType<typeof fetchStats>> | null = null;
  try {
    stats = await fetchStats();
  } catch {
    // backend may not be available during SSR/build
  }

  return (
    <aside className="w-60 shrink-0 flex flex-col border-r border-zinc-800 bg-zinc-900 sticky top-0 h-screen overflow-y-auto">
      {/* Logo */}
      <div className="px-4 pt-5 pb-4">
        <Link
          href="/"
          className="flex items-center gap-2 group"
          aria-label="AiApiRadar home"
        >
          <span className="text-blue-400 text-lg leading-none select-none">⬡</span>
          <span className="text-zinc-100 font-semibold text-sm tracking-tight group-hover:text-white transition-colors">
            AiApiRadar
          </span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="px-2 flex flex-col gap-0.5" aria-label="Main navigation">
        <NavLink href="/" icon={<Zap size={14} />} label="Feed" />
        <NavLink href="/stats" icon={<BarChart3 size={14} />} label="Analytics" />
        <NavLink href="/settings" icon={<Settings size={14} />} label="Settings" />
      </nav>

      {/* Divider */}
      <div className="mx-4 my-4 border-t border-zinc-800" />

      {/* Stats overview */}
      <section className="px-4 mb-4" aria-label="Stats overview">
        <p className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-2">
          Overview
        </p>
        <dl className="flex flex-col gap-1.5">
          <div className="flex justify-between text-xs">
            <dt className="text-zinc-400">Services</dt>
            <dd className="text-zinc-200 tabular-nums font-medium">
              {stats?.services ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between text-xs">
            <dt className="text-zinc-400">Active</dt>
            <dd className="text-emerald-400 tabular-nums font-medium">
              {stats?.active ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between text-xs">
            <dt className="text-zinc-400">Dead</dt>
            <dd className="text-red-400 tabular-nums font-medium">
              {stats?.dead ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between text-xs">
            <dt className="text-zinc-400">Offers</dt>
            <dd className="text-zinc-200 tabular-nums font-medium">
              {stats?.offers ?? "—"}
            </dd>
          </div>
        </dl>
      </section>

      {/* Sources */}
      <section className="px-4 mb-4" aria-label="Data sources">
        <p className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-2">
          Sources
        </p>
        <ul className="flex flex-col gap-1.5">
          {SOURCES.map(({ key, label, dot }) => (
            <li key={key} className="flex items-center gap-2 text-xs">
              <span
                className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`}
                aria-hidden="true"
              />
              <span className="text-zinc-400">{label}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Push version to bottom */}
      <div className="flex-1" />

      {/* Version — baked in at build time from the root VERSION file */}
      <div className="px-4 py-3 border-t border-zinc-800/50">
        <p className="text-[11px] text-zinc-600 tabular-nums">
          v{process.env.NEXT_PUBLIC_BUILD_VERSION ?? "dev"}
        </p>
      </div>
    </aside>
  );
}
