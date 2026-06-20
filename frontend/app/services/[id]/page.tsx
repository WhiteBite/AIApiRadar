import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { fetchService } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { StatusBadge } from "@/components/ui/status-badge";
import { TypeBadge } from "@/components/ui/type-badge";
import { ScoreBar } from "@/components/ui/score-bar";
import { ModelTag } from "@/components/ui/model-tag";
import { timeAgo } from "@/lib/utils";

// ─── Helpers ─────────────────────────────────────────────────────────────────
function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">
        {title}
      </h2>
      {children}
    </section>
  );
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2 border-b border-zinc-800 last:border-0">
      <span className="text-xs text-zinc-500 w-28 shrink-0 pt-0.5">{label}</span>
      <span className="text-sm text-zinc-200 flex-1">{value}</span>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default async function ServicePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let service: Awaited<ReturnType<typeof fetchService>> | null = null;
  try {
    service = await fetchService(Number(id));
  } catch {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <p className="text-zinc-500">Service not found.</p>
      </div>
    );
  }

  const title = service.name ?? service.domain;
  const subtitle = `${service.domain} · ${service.offers.length} offer${service.offers.length !== 1 ? "s" : ""}`;

  return (
    <div className="min-h-screen bg-zinc-950">
      <Header title={title} subtitle={subtitle} />

      <div className="px-6 py-6 max-w-4xl space-y-8">
        {/* Back */}
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to feed
        </Link>

        {/* Service info */}
        <Section title="Service">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-5 py-1">
            <MetaRow label="Domain" value={service.domain} />
            <MetaRow label="Status" value={<StatusBadge status={service.status} />} />
            <MetaRow label="Type" value={<TypeBadge type={service.type} />} />
            {service.engine && <MetaRow label="Engine" value={service.engine} />}
            <MetaRow
              label="Reliability"
              value={
                <div className="pt-1 w-48">
                  <ScoreBar score={service.reliability} />
                </div>
              }
            />
            {service.domain_first_seen && (
              <MetaRow
                label="Domain first seen"
                value={new Date(service.domain_first_seen).toLocaleDateString()}
              />
            )}
          </div>
        </Section>

        {/* Offers */}
        <Section title={`Offers (${service.offers.length})`}>
          {service.offers.length === 0 ? (
            <p className="text-sm text-zinc-600">No offers recorded.</p>
          ) : (
            <div className="space-y-3">
              {service.offers.map((offer) => (
                <div
                  key={offer.id}
                  className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <TypeBadge type={offer.type} />
                      {offer.amount && (
                        <span className="text-lg font-bold text-emerald-400 tabular-nums">
                          {offer.currency ?? "$"}{Math.round(offer.amount)}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={offer.status} />
                      {offer.url && (
                        <a
                          href={offer.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-zinc-400 hover:text-zinc-200 flex items-center gap-1"
                        >
                          Open <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>

                  {offer.models.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {offer.models.map((m) => <ModelTag key={m} model={m} />)}
                    </div>
                  )}

                  {offer.claim_steps && (
                    <p className="text-sm text-zinc-400 leading-relaxed">
                      {offer.claim_steps}
                    </p>
                  )}

                  {offer.referral_required && (
                    <p className="text-xs text-amber-400/80">⚠ referral required</p>
                  )}

                  <div className="space-y-1.5 pt-1">
                    {offer.reliability !== null && (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-zinc-500 w-16">Reliability</span>
                        <ScoreBar score={offer.reliability ?? 0} className="flex-1" />
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-zinc-500 w-16">Score</span>
                      <ScoreBar score={offer.score} className="flex-1" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* Signals timeline */}
        <Section title={`Signals (${service.signals.length})`}>
          {service.signals.length === 0 ? (
            <p className="text-sm text-zinc-600">No signals recorded.</p>
          ) : (
            <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-800">
                    <th className="text-left px-4 py-2.5 text-xs text-zinc-500 font-medium">Source</th>
                    <th className="text-left px-4 py-2.5 text-xs text-zinc-500 font-medium">Observed</th>
                    <th className="text-left px-4 py-2.5 text-xs text-zinc-500 font-medium">Link</th>
                  </tr>
                </thead>
                <tbody>
                  {service.signals.map((sig, i) => (
                    <tr
                      key={i}
                      className="border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30"
                    >
                      <td className="px-4 py-2.5 text-zinc-300 font-medium">{sig.source}</td>
                      <td className="px-4 py-2.5 text-zinc-500 tabular-nums text-xs">
                        {sig.observed_at ? timeAgo(sig.observed_at) : "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        {sig.source_url ? (
                          <a
                            href={sig.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-zinc-500 hover:text-zinc-300 truncate max-w-xs inline-block"
                          >
                            {sig.source_url.length > 60
                              ? sig.source_url.slice(0, 60) + "…"
                              : sig.source_url}
                          </a>
                        ) : (
                          <span className="text-zinc-700">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
