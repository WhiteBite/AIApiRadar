"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Radio, Check, RotateCcw, ChevronDown, ChevronUp, Plus } from "lucide-react";

import {
  fetchSources, createSource, updateSource, deleteSource,
  fetchCollectors, patchCollector, fetchKeyStatus,
  fetchSettings, patchSettings,
  apiKeys,
} from "@/lib/api";
import type { CollectorItem, AppSettings } from "@/lib/api";
import type { SourceItem } from "@/lib/types";
import { Header } from "@/components/layout/header";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";

// ── Color map ─────────────────────────────────────────────────────────────────
const DOT: Record<string, string> = {
  cyan: "bg-cyan-400", orange: "bg-orange-400", red: "bg-red-400",
  yellow: "bg-yellow-400", lime: "bg-lime-400", purple: "bg-purple-400",
  sky: "bg-sky-400", zinc: "bg-zinc-400", blue: "bg-blue-400",
  violet: "bg-violet-400",
};
const dotClass = (d: string) => DOT[d] ?? "bg-zinc-400";

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatInterval(seconds: number): string {
  if (seconds >= 3600) return `${Math.round(seconds / 3600)} ч`;
  return `${Math.round(seconds / 60)} мин`;
}

function testPrefilter(
  text: string,
  s: Pick<AppSettings, "prefilter_zh_strong" | "prefilter_zh_weak" | "prefilter_ru" | "prefilter_en_strong" | "prefilter_en_weak">
): { pass: boolean; hits: string[] } {
  const low = text.toLowerCase();
  for (const kw of s.prefilter_zh_strong) if (low.includes(kw)) return { pass: true, hits: [kw] };
  const zhWeak = s.prefilter_zh_weak.filter(k => low.includes(k));
  if (zhWeak.length >= 2) return { pass: true, hits: zhWeak };
  const ru = s.prefilter_ru.filter(k => low.includes(k));
  if (ru.length > 0) return { pass: true, hits: ru };
  const enStrong = s.prefilter_en_strong.filter(k => low.includes(k));
  if (enStrong.length > 0) return { pass: true, hits: enStrong };
  const enWeak = s.prefilter_en_weak.filter(k => low.includes(k));
  const hasMoney = /\$\s?\d+|\d+\s*(?:credits?|tokens?)/i.test(text);
  if (hasMoney) enWeak.push("$money");
  if (enWeak.length >= 2) return { pass: true, hits: enWeak };
  return { pass: false, hits: [] };
}

// ── ChipEditor ────────────────────────────────────────────────────────────────
function ChipEditor({ items, onChange }: { items: string[]; onChange: (v: string[]) => void }) {
  const [input, setInput] = useState("");
  const add = () => {
    const v = input.trim().toLowerCase();
    if (v && !items.includes(v)) onChange([...items, v]);
    setInput("");
  };
  return (
    <div className="flex flex-wrap gap-1.5 p-3 rounded-lg bg-zinc-900/50 border border-zinc-800 min-h-[60px]">
      {items.map(kw => (
        <span
          key={kw}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-zinc-800 border border-zinc-700 text-xs text-zinc-300"
        >
          {kw}
          <button
            onClick={() => onChange(items.filter(k => k !== kw))}
            className="text-zinc-500 hover:text-red-400 ml-0.5 leading-none"
          >
            ×
          </button>
        </span>
      ))}
      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); }
        }}
        onBlur={add}
        placeholder="Добавить…"
        className="bg-transparent outline-none text-xs text-zinc-300 placeholder:text-zinc-600 w-24 shrink-0"
      />
    </div>
  );
}

// ── SavedBadge ────────────────────────────────────────────────────────────────
function SavedBadge({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-emerald-400">
      <Check className="w-3 h-3" /> Сохранено
    </span>
  );
}

// ── SliderRow ─────────────────────────────────────────────────────────────────
function SliderRow({
  label, value, onChange,
}: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 text-sm text-zinc-300 shrink-0">{label}</span>
      <input
        type="range" min={0} max={1} step={0.01}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="flex-1 accent-zinc-400"
      />
      <span className="w-12 text-right text-sm font-mono text-zinc-300 shrink-0">
        {value.toFixed(2)}
      </span>
    </div>
  );
}

// ── CollapsibleSection ────────────────────────────────────────────────────────
function CollapsibleSection({
  title, badge, defaultOpen = true, children,
}: { title: string; badge?: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-zinc-900/60 hover:bg-zinc-800/40 transition-colors text-left"
      >
        <span className="text-sm font-medium text-zinc-200">{title}</span>
        <div className="flex items-center gap-2">
          {badge && <span className="text-xs text-zinc-500">{badge}</span>}
          {open ? <ChevronUp className="w-4 h-4 text-zinc-500" /> : <ChevronDown className="w-4 h-4 text-zinc-500" />}
        </div>
      </button>
      {open && <div className="px-4 pb-4 pt-3">{children}</div>}
    </div>
  );
}

// ── CollectorRow ──────────────────────────────────────────────────────────────
function CollectorRow({ collector: c, onToggle }: { collector: CollectorItem; onToggle: () => void }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass(c.dot)}`} />
      <div className="flex-1 min-w-0 flex items-center gap-2">
        <span className="text-sm text-zinc-300 truncate">{c.label}</span>
        <span className="text-[10px] text-zinc-600 shrink-0">{formatInterval(c.interval)}</span>
        {c.mode === "stream" && (
          <Tooltip content="Требует долгоживущий процесс. Не работает на Cloudflare/CI.">
            <span className="text-[10px] text-zinc-600 border border-zinc-700 px-1 rounded cursor-help">
              stream
            </span>
          </Tooltip>
        )}
      </div>
      {c.requires && (
        <Tooltip content={`Требует ключ: ${c.requires}`}>
          <span className="text-[10px] text-amber-500/80 border border-amber-500/20 px-1.5 py-0.5 rounded cursor-help">
            нужен ключ
          </span>
        </Tooltip>
      )}
      <button
        onClick={onToggle}
        className={`text-xs px-2 py-1 rounded-md border transition-colors ${c.enabled
          ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"
          : "border-zinc-700 text-zinc-500"
          }`}
      >
        {c.enabled ? "вкл" : "выкл"}
      </button>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const qc = useQueryClient();

  // ── Sources (Telegram channels) ──────────────────────────────────────────
  const [channel, setChannel] = useState("");
  const [topic, setTopic] = useState("");

  const { data: sourcesData } = useQuery({
    queryKey: apiKeys.sources(),
    queryFn: () => fetchSources(),
  });
  const tgSources: SourceItem[] = (sourcesData?.items ?? []).filter((s: SourceItem) => s.type === "telegram");
  const invalidateSources = useCallback(
    () => qc.invalidateQueries({ queryKey: apiKeys.sources() }), [qc]
  );

  const addSourceMut = useMutation({
    mutationFn: () => createSource({
      type: "telegram",
      channel: channel.trim(),
      topic_id: topic.trim() ? Number(topic.trim()) : undefined,
    }),
    onSuccess: () => { setChannel(""); setTopic(""); invalidateSources(); },
  });

  const toggleSourceMut = useMutation({
    mutationFn: (s: SourceItem) => updateSource(s.id, { enabled: !s.enabled }),
    onSuccess: invalidateSources,
  });

  const delSourceMut = useMutation({
    mutationFn: (id: number) => deleteSource(id),
    onSuccess: invalidateSources,
  });

  // ── Collectors ────────────────────────────────────────────────────────────
  const { data: collectors = [], isLoading: collectorsLoading } = useQuery({
    queryKey: apiKeys.collectors(),
    queryFn: fetchCollectors,
  });

  const toggleCollectorMut = useMutation({
    mutationFn: (c: CollectorItem) => patchCollector(c.name, { enabled: !c.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeys.collectors() }),
  });

  const pollCollectors = collectors.filter(c => c.mode !== "stream");
  const streamCollectors = collectors.filter(c => c.mode === "stream");

  // ── API key status ────────────────────────────────────────────────────────
  const { data: keyList = [] } = useQuery({
    queryKey: apiKeys.keyStatus(),
    queryFn: fetchKeyStatus,
  });

  // ── App settings ─────────────────────────────────────────────────────────
  const { data: serverSettings } = useQuery({
    queryKey: apiKeys.settings(),
    queryFn: fetchSettings,
  });

  const settingsMut = useMutation({
    mutationFn: patchSettings,
    onSuccess: (_data, patch) => {
      qc.setQueryData(apiKeys.settings(), (old: AppSettings | undefined) =>
        old ? { ...old, ...patch } : old
      );
    },
  });

  // ── Keywords tab local state ──────────────────────────────────────────────
  const [kwEnStrong, setKwEnStrong] = useState<string[]>([]);
  const [kwEnWeak, setKwEnWeak] = useState<string[]>([]);
  const [kwRu, setKwRu] = useState<string[]>([]);
  const [kwZhStrong, setKwZhStrong] = useState<string[]>([]);
  const [kwZhWeak, setKwZhWeak] = useState<string[]>([]);
  const [kwDirty, setKwDirty] = useState(false);
  const [kwSaved, setKwSaved] = useState(false);

  // ── Scoring tab local state ───────────────────────────────────────────────
  const [wFresh, setWFresh] = useState(0.4);
  const [wAmount, setWAmount] = useState(0.3);
  const [wEase, setWEase] = useState(0.2);
  const [wReliab, setWReliab] = useState(0.1);
  const [earlyBoostVal, setEarlyBoostVal] = useState(0.1);
  const [earlyBoostOn, setEarlyBoostOn] = useState(true);
  const [scoreSaved, setScoreSaved] = useState(false);
  const scoreTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Discovery tab local state ─────────────────────────────────────────────
  const [discLimit, setDiscLimit] = useState(40);
  const [notifyScore, setNotifyScore] = useState(0.6);
  const [discDirty, setDiscDirty] = useState(false);
  const [discSaved, setDiscSaved] = useState(false);

  // ── Live prefilter test ───────────────────────────────────────────────────
  const [testText, setTestText] = useState("");

  const liveSettings: Pick<
    AppSettings,
    "prefilter_zh_strong" | "prefilter_zh_weak" | "prefilter_ru" | "prefilter_en_strong" | "prefilter_en_weak"
  > = {
    prefilter_zh_strong: kwZhStrong,
    prefilter_zh_weak: kwZhWeak,
    prefilter_ru: kwRu,
    prefilter_en_strong: kwEnStrong,
    prefilter_en_weak: kwEnWeak,
  };
  const testResult = testText.trim() ? testPrefilter(testText, liveSettings) : null;

  // ── Init local state from server ──────────────────────────────────────────
  const initDoneRef = useRef(false);
  useEffect(() => {
    if (!serverSettings || initDoneRef.current) return;
    initDoneRef.current = true;
    setKwEnStrong(serverSettings.prefilter_en_strong);
    setKwEnWeak(serverSettings.prefilter_en_weak);
    setKwRu(serverSettings.prefilter_ru);
    setKwZhStrong(serverSettings.prefilter_zh_strong);
    setKwZhWeak(serverSettings.prefilter_zh_weak);
    setWFresh(serverSettings.score_w_freshness);
    setWAmount(serverSettings.score_w_amount);
    setWEase(serverSettings.score_w_ease);
    setWReliab(serverSettings.score_w_reliability);
    const boost = serverSettings.early_signal_boost;
    setEarlyBoostOn(boost > 0);
    setEarlyBoostVal(boost > 0 ? boost : 0.1);
    setDiscLimit(serverSettings.discovery_limit);
    setNotifyScore(serverSettings.notify_min_score);
  }, [serverSettings]);

  // ── Score weight normalization ────────────────────────────────────────────
  // When dragging one weight, redistribute the remainder proportionally.
  function changeWeight(key: "fresh" | "amount" | "ease" | "reliab", newVal: number) {
    const clamped = Math.max(0, Math.min(1, newVal));
    const current = { fresh: wFresh, amount: wAmount, ease: wEase, reliab: wReliab };
    const others = (Object.keys(current) as Array<keyof typeof current>).filter(k => k !== key);
    const othersSum = others.reduce((s, k) => s + current[k], 0);
    const remaining = Math.max(0, 1 - clamped);
    const next = { ...current, [key]: clamped };
    if (othersSum > 0) {
      for (const k of others) {
        next[k] = Math.round((current[k] / othersSum) * remaining * 1000) / 1000;
      }
      // Fix rounding residual on last key
      const sum = (Object.values(next) as number[]).reduce((a, b) => a + b, 0);
      const lastKey = others[others.length - 1];
      next[lastKey] = Math.round((next[lastKey] + (1 - sum)) * 1000) / 1000;
    }
    setWFresh(next.fresh);
    setWAmount(next.amount);
    setWEase(next.ease);
    setWReliab(next.reliab);
    scheduleScoreSave(next.fresh, next.amount, next.ease, next.reliab, earlyBoostOn ? earlyBoostVal : 0);
  }

  // ── Scoring auto-save (600 ms debounce) ──────────────────────────────────
  const scheduleScoreSave = useCallback((
    f: number, a: number, e: number, r: number, boost: number
  ) => {
    if (scoreTimerRef.current) clearTimeout(scoreTimerRef.current);
    scoreTimerRef.current = setTimeout(() => {
      settingsMut.mutate(
        { score_w_freshness: f, score_w_amount: a, score_w_ease: e, score_w_reliability: r, early_signal_boost: boost },
        { onSuccess: () => { setScoreSaved(true); setTimeout(() => setScoreSaved(false), 2000); } }
      );
    }, 600);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleEarlyBoostChange(on: boolean, val: number) {
    setEarlyBoostOn(on);
    setEarlyBoostVal(val);
    scheduleScoreSave(wFresh, wAmount, wEase, wReliab, on ? val : 0);
  }

  const weightSum = Math.round((wFresh + wAmount + wEase + wReliab) * 1000) / 1000;

  // ── Keywords save ─────────────────────────────────────────────────────────
  function saveKeywords() {
    settingsMut.mutate(
      {
        prefilter_en_strong: kwEnStrong,
        prefilter_en_weak: kwEnWeak,
        prefilter_ru: kwRu,
        prefilter_zh_strong: kwZhStrong,
        prefilter_zh_weak: kwZhWeak,
      },
      {
        onSuccess: () => {
          setKwDirty(false);
          setKwSaved(true);
          setTimeout(() => setKwSaved(false), 2000);
        },
      }
    );
  }

  // ── Discovery save ────────────────────────────────────────────────────────
  function saveDiscovery() {
    settingsMut.mutate(
      { discovery_limit: discLimit, notify_min_score: notifyScore },
      {
        onSuccess: () => {
          setDiscDirty(false);
          setDiscSaved(true);
          setTimeout(() => setDiscSaved(false), 2000);
        },
      }
    );
  }

  // ── Reset helpers ─────────────────────────────────────────────────────────
  function resetKeywords() {
    if (!serverSettings) return;
    setKwEnStrong(serverSettings.prefilter_en_strong);
    setKwEnWeak(serverSettings.prefilter_en_weak);
    setKwRu(serverSettings.prefilter_ru);
    setKwZhStrong(serverSettings.prefilter_zh_strong);
    setKwZhWeak(serverSettings.prefilter_zh_weak);
    setKwDirty(false);
  }

  function resetScoring() {
    setWFresh(0.4); setWAmount(0.3); setWEase(0.2); setWReliab(0.1);
    setEarlyBoostOn(true); setEarlyBoostVal(0.1);
    scheduleScoreSave(0.4, 0.3, 0.2, 0.1, 0.1);
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col overflow-hidden">
      <Header title="Настройки" subtitle="Источники, фильтры, скоринг" />

      <Tabs defaultValue="sources" className="flex flex-col flex-1 overflow-hidden">
        <TabsList className="shrink-0">
          <TabsTrigger value="sources">Источники</TabsTrigger>
          <TabsTrigger value="keywords">Ключевые слова</TabsTrigger>
          <TabsTrigger value="scoring">Скоринг</TabsTrigger>
          <TabsTrigger value="discovery">Discovery</TabsTrigger>
          <TabsTrigger value="notifications">Уведомления</TabsTrigger>
        </TabsList>

        {/* ══════════════════════════════ TAB: SOURCES ═══════════════════════ */}
        <TabsContent value="sources" className="flex-1 overflow-y-auto">
          <div className="max-w-2xl px-6 py-6 space-y-10">

            {/* Telegram channels */}
            <section>
              <h2 className="text-sm font-semibold text-zinc-200 mb-1">📱 Telegram-каналы</h2>
              <p className="text-sm text-zinc-500 mb-4">
                Добавь каналы или конкретные темы для мониторинга. Для реального ингеста
                нужны API-ключи Telegram (в{" "}
                <code className="text-xs bg-zinc-800 px-1 rounded">.env</code>).
              </p>
              <div className="flex gap-2 mb-4">
                <Input
                  placeholder="@канал или ссылка"
                  value={channel}
                  onChange={e => setChannel(e.target.value)}
                  className="flex-1"
                />
                <Input
                  placeholder="тема (id, опц.)"
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  className="w-32"
                />
                <Button
                  onClick={() => channel.trim() && addSourceMut.mutate()}
                  disabled={!channel.trim() || addSourceMut.isPending}
                >
                  <Plus className="w-4 h-4" /> Добавить
                </Button>
              </div>
              {tgSources.length === 0 ? (
                <p className="text-sm text-zinc-600 italic">Каналы ещё не добавлены.</p>
              ) : (
                <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
                  {tgSources.map(s => (
                    <div key={s.id} className="flex items-center gap-3 px-4 py-2.5">
                      <Radio className="w-4 h-4 text-zinc-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-zinc-200 font-medium truncate">{s.name}</div>
                        <div className="text-xs text-zinc-500">
                          {s.config.topic_id ? `тема ${s.config.topic_id}` : "весь канал"}
                        </div>
                      </div>
                      <button
                        onClick={() => toggleSourceMut.mutate(s)}
                        className={`text-xs px-2 py-1 rounded-md border transition-colors ${s.enabled
                          ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"
                          : "border-zinc-700 text-zinc-500"
                          }`}
                      >
                        {s.enabled ? "вкл" : "выкл"}
                      </button>
                      <button
                        onClick={() => delSourceMut.mutate(s.id)}
                        className="text-zinc-600 hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Collectors */}
            <section>
              <h2 className="text-sm font-semibold text-zinc-200 mb-4">⚙️ Коллекторы</h2>
              {collectorsLoading ? (
                <p className="text-sm text-zinc-600">Загрузка...</p>
              ) : (
                <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
                  {pollCollectors.map(c => (
                    <CollectorRow
                      key={c.name}
                      collector={c}
                      onToggle={() => toggleCollectorMut.mutate(c)}
                    />
                  ))}
                  {streamCollectors.length > 0 && (
                    <>
                      <div className="px-4 py-2 bg-zinc-900/70 flex items-center gap-2">
                        <span className="text-[10px] uppercase tracking-widest text-zinc-600 font-semibold">
                          Только VDS
                        </span>
                        <Tooltip content="Требует долгоживущий процесс. Не работает на Cloudflare/CI.">
                          <span className="text-zinc-600 text-[11px] cursor-help underline decoration-dotted">
                            ?
                          </span>
                        </Tooltip>
                      </div>
                      {streamCollectors.map(c => (
                        <CollectorRow
                          key={c.name}
                          collector={c}
                          onToggle={() => toggleCollectorMut.mutate(c)}
                        />
                      ))}
                    </>
                  )}
                </div>
              )}
            </section>

            {/* API Keys */}
            <section>
              <h2 className="text-sm font-semibold text-zinc-200 mb-4">🔑 Ключи API</h2>
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
                {keyList.map(k => (
                  <div key={k.key} className="flex items-center gap-3 px-4 py-2.5">
                    <code className="text-xs text-zinc-400 font-mono flex-1 truncate">{k.key}</code>
                    <span className={`text-xs ${k.present ? "text-emerald-400" : "text-red-400"}`}>
                      {k.present ? "✓" : "✗"}
                    </span>
                    <span className="text-xs text-zinc-500 truncate max-w-[200px]">
                      {k.unlocks.join(", ")}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </TabsContent>

        {/* ═════════════════════════ TAB: KEYWORDS ══════════════════════════ */}
        <TabsContent value="keywords" className="flex-1 overflow-y-auto">
          <div className="max-w-2xl px-6 py-6 space-y-6">
            {/* Info banner */}
            <div className="flex gap-3 rounded-xl border border-blue-500/20 bg-blue-500/5 px-4 py-3">
              <span className="text-base leading-none mt-0.5">ℹ️</span>
              <p className="text-sm text-zinc-400">
                Определяют что считается оффером. Изменения применятся при следующем запуске (~1ч).
              </p>
            </div>

            {/* Keyword groups */}
            <CollapsibleSection title="🟢 EN Strong" badge="Один ключ = немедленный пропуск">
              <ChipEditor items={kwEnStrong} onChange={v => { setKwEnStrong(v); setKwDirty(true); }} />
            </CollapsibleSection>

            <CollapsibleSection title="🔵 EN Weak" badge="Нужны 2+ слова чтобы пройти">
              <ChipEditor items={kwEnWeak} onChange={v => { setKwEnWeak(v); setKwDirty(true); }} />
            </CollapsibleSection>

            <CollapsibleSection title="🔴 RU" badge="Любое слово = пропуск">
              <ChipEditor items={kwRu} onChange={v => { setKwRu(v); setKwDirty(true); }} />
            </CollapsibleSection>

            <CollapsibleSection title="🟡 ZH Strong" badge="Высокий сигнал, китайская сцена">
              <ChipEditor items={kwZhStrong} onChange={v => { setKwZhStrong(v); setKwDirty(true); }} />
            </CollapsibleSection>

            {/* Action bar */}
            <div className="flex items-center gap-3 pt-2">
              <Button
                onClick={saveKeywords}
                disabled={!kwDirty || settingsMut.isPending}
              >
                Сохранить
              </Button>
              <SavedBadge visible={kwSaved} />
              <button
                onClick={resetKeywords}
                className="ml-auto inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Сбросить к дефолтам
              </button>
            </div>

            {/* Live test */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
              <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">
                Live-тест фильтра
              </p>
              <textarea
                value={testText}
                onChange={e => setTestText(e.target.value)}
                placeholder="Вставь текст из поста…"
                rows={3}
                className="w-full rounded-lg bg-zinc-950 border border-zinc-800 px-3 py-2 text-sm text-zinc-300 placeholder:text-zinc-600 outline-none resize-none focus:border-zinc-600 transition-colors"
              />
              {testResult && (
                <div className={`flex items-start gap-2 text-sm rounded-lg px-3 py-2 ${testResult.pass
                  ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300"
                  : "bg-red-500/10 border border-red-500/20 text-red-300"
                  }`}>
                  <span className="text-base leading-none">{testResult.pass ? "✅" : "❌"}</span>
                  <div>
                    <span className="font-medium">{testResult.pass ? "Пройдёт фильтр" : "Будет отфильтрован"}</span>
                    {testResult.hits.length > 0 && (
                      <span className="ml-2 text-xs opacity-70">
                        совпадения: {testResult.hits.join(", ")}
                      </span>
                    )}
                  </div>
                </div>
              )}
              {!testResult && testText.trim() === "" && (
                <p className="text-xs text-zinc-600 italic">Введи текст выше чтобы проверить.</p>
              )}
            </div>
          </div>
        </TabsContent>

        {/* ══════════════════════════ TAB: SCORING ══════════════════════════ */}
        <TabsContent value="scoring" className="flex-1 overflow-y-auto">
          <div className="max-w-2xl px-6 py-6 space-y-8">
            {/* Weights */}
            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-zinc-200">⚖️ Веса скоринга</h2>
                <div className="flex items-center gap-3">
                  <span className={`text-xs ${Math.abs(weightSum - 1) < 0.005 ? "text-emerald-400" : "text-amber-400"}`}>
                    Сумма: {weightSum.toFixed(3)} {Math.abs(weightSum - 1) < 0.005 ? "✓" : "≠ 1"}
                  </span>
                  <SavedBadge visible={scoreSaved} />
                </div>
              </div>
              <p className="text-sm text-zinc-500">
                Веса определяют что показывается первым. Автосохранение через 600 мс.
              </p>
              <div className="space-y-3">
                <SliderRow label="Свежесть" value={wFresh} onChange={v => changeWeight("fresh", v)} />
                <SliderRow label="Сумма бонуса" value={wAmount} onChange={v => changeWeight("amount", v)} />
                <SliderRow label="Простота" value={wEase} onChange={v => changeWeight("ease", v)} />
                <SliderRow label="Надёжность" value={wReliab} onChange={v => changeWeight("reliab", v)} />
              </div>
              <button
                onClick={resetScoring}
                className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" /> Сбросить к дефолтам
              </button>
            </section>

            {/* Early signal boost */}
            <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 cursor-pointer flex-1">
                  <button
                    role="switch"
                    aria-checked={earlyBoostOn}
                    onClick={() => handleEarlyBoostChange(!earlyBoostOn, earlyBoostVal)}
                    className={`relative inline-flex h-5 w-9 rounded-full transition-colors focus:outline-none ${earlyBoostOn ? "bg-zinc-400" : "bg-zinc-700"
                      }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform mt-0.5 ${earlyBoostOn ? "translate-x-4" : "translate-x-0.5"
                        }`}
                    />
                  </button>
                  <span className="text-sm text-zinc-300 font-medium">Early signal boost</span>
                </label>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-zinc-500">+</span>
                  <input
                    type="number"
                    min={0} max={0.5} step={0.01}
                    value={earlyBoostVal}
                    disabled={!earlyBoostOn}
                    onChange={e => {
                      const v = Math.max(0, Math.min(0.5, Number(e.target.value)));
                      setEarlyBoostVal(v);
                      if (earlyBoostOn) scheduleScoreSave(wFresh, wAmount, wEase, wReliab, v);
                    }}
                    className="w-16 bg-zinc-950 border border-zinc-800 rounded px-2 py-0.5 text-xs text-zinc-300 text-right outline-none focus:border-zinc-600 disabled:opacity-40"
                  />
                </div>
              </div>
              <p className="text-xs text-zinc-500">
                Буст для zh/ru постов без английских сигналов — офферы появляются в Telegram/Chinese
                раньше чем в HN/Reddit.
              </p>
            </section>
          </div>
        </TabsContent>

        {/* ════════════════════════ TAB: DISCOVERY ══════════════════════════ */}
        <TabsContent value="discovery" className="flex-1 overflow-y-auto">
          <div className="max-w-2xl px-6 py-6 space-y-8">
            <section className="space-y-6">
              <h2 className="text-sm font-semibold text-zinc-200 mb-2">🔍 Discovery</h2>

              {/* discovery_limit */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
                <label className="text-sm font-medium text-zinc-300" htmlFor="disc-limit">
                  Лимит доменов
                </label>
                <p className="text-xs text-zinc-500">
                  Максимум доменов на пробу за один запуск пайплайна.
                </p>
                <input
                  id="disc-limit"
                  type="number"
                  min={1} max={500}
                  value={discLimit}
                  onChange={e => { setDiscLimit(Number(e.target.value)); setDiscDirty(true); }}
                  className="w-32 bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-1.5 text-sm text-zinc-300 outline-none focus:border-zinc-600 transition-colors"
                />
              </div>

              {/* notify_min_score */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-zinc-300">
                    Минимальный score для уведомлений
                  </label>
                  <span className="text-sm font-mono text-zinc-300">{notifyScore.toFixed(2)}</span>
                </div>
                <input
                  type="range" min={0} max={1} step={0.01}
                  value={notifyScore}
                  onChange={e => { setNotifyScore(Number(e.target.value)); setDiscDirty(true); }}
                  className="w-full accent-zinc-400"
                />
                <p className="text-xs text-zinc-500">
                  При текущем пороге: офферы со score ≥ {notifyScore.toFixed(2)} попадут в уведомления.
                </p>
              </div>
            </section>

            {/* Save row */}
            <div className="flex items-center gap-3">
              <Button
                onClick={saveDiscovery}
                disabled={!discDirty || settingsMut.isPending}
              >
                Сохранить
              </Button>
              <SavedBadge visible={discSaved} />
            </div>
          </div>
        </TabsContent>

        {/* ══════════════════════ TAB: NOTIFICATIONS ════════════════════════ */}
        <TabsContent value="notifications" className="flex-1 overflow-y-auto">
          <div className="max-w-2xl px-6 py-6 space-y-6">
            <section>
              <h2 className="text-sm font-semibold text-zinc-200 mb-1">🔔 Telegram уведомления</h2>
              <p className="text-sm text-zinc-500 mb-4">
                Автоматическая рассылка свежих офферов в Telegram-чат после каждого запуска коллекторов.
              </p>

              <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 space-y-3">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 text-lg leading-none">🔐</span>
                  <div>
                    <p className="text-sm text-zinc-300 font-medium mb-1">
                      Уведомления настраиваются через GitHub Secrets
                    </p>
                    <p className="text-sm text-zinc-500">
                      Установи секреты{" "}
                      <code className="text-xs bg-zinc-800 border border-zinc-700 px-1.5 py-0.5 rounded text-zinc-200">
                        TG_BOT_TOKEN
                      </code>{" "}
                      и{" "}
                      <code className="text-xs bg-zinc-800 border border-zinc-700 px-1.5 py-0.5 rounded text-zinc-200">
                        TG_CHAT_ID
                      </code>{" "}
                      в настройках репозитория, и уведомления заработают автоматически.
                    </p>
                  </div>
                </div>
                <div className="border-t border-zinc-800 pt-3 flex items-center gap-2 text-sm text-zinc-400">
                  <span className="text-zinc-500">Что отправляется:</span>
                  <span>Свежие офферы с score ≥ {notifyScore.toFixed(2)}, до 5 в час</span>
                </div>
              </div>

              <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-3">
                  Как настроить
                </p>
                <ol className="text-sm text-zinc-400 space-y-1.5 list-decimal list-inside mb-3">
                  <li>
                    Создай бота через <span className="text-zinc-300">@BotFather</span> и получи токен
                  </li>
                  <li>
                    Добавь бота в нужный чат и получи{" "}
                    <code className="text-xs bg-zinc-800 px-1 rounded">chat_id</code>
                  </li>
                  <li>Добавь секреты в репозиторий:</li>
                </ol>
                <pre className="bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 text-xs text-zinc-300 font-mono overflow-x-auto">
                  <code>{`gh secret set TG_BOT_TOKEN\ngh secret set TG_CHAT_ID`}</code>
                </pre>
              </div>
            </section>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
