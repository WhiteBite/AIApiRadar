"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Radio } from "lucide-react";

import {
  fetchSources, createSource, updateSource, deleteSource,
  fetchCollectors, patchCollector, fetchKeyStatus,
  apiKeys,
} from "@/lib/api";
import type { CollectorItem } from "@/lib/api";
import type { SourceItem } from "@/lib/types";
import { Header } from "@/components/layout/header";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const DOT: Record<string, string> = {
  cyan: "bg-cyan-400", orange: "bg-orange-400", red: "bg-red-400",
  yellow: "bg-yellow-400", lime: "bg-lime-400", purple: "bg-purple-400",
  sky: "bg-sky-400", zinc: "bg-zinc-400", blue: "bg-blue-400",
  violet: "bg-violet-400",
};
const dotClass = (d: string) => DOT[d] ?? "bg-zinc-400";

export default function SettingsPage() {
  const qc = useQueryClient();
  const [channel, setChannel] = useState("");
  const [topic, setTopic] = useState("");

  const { data } = useQuery({
    queryKey: apiKeys.sources(),
    queryFn: () => fetchSources(),
  });
  const sources = data?.items ?? [];
  const tg = sources.filter((s) => s.type === "telegram");

  const invalidate = () => qc.invalidateQueries({ queryKey: apiKeys.sources() });

  const addMut = useMutation({
    mutationFn: () =>
      createSource({
        type: "telegram",
        channel: channel.trim(),
        topic_id: topic.trim() ? Number(topic.trim()) : undefined,
      }),
    onSuccess: () => { setChannel(""); setTopic(""); invalidate(); },
  });

  const toggleMut = useMutation({
    mutationFn: (s: SourceItem) => updateSource(s.id, { enabled: !s.enabled }),
    onSuccess: invalidate,
  });

  const delMut = useMutation({
    mutationFn: (id: number) => deleteSource(id),
    onSuccess: invalidate,
  });

  // Collectors
  const { data: collectors = [], isLoading } = useQuery({
    queryKey: apiKeys.collectors(),
    queryFn: fetchCollectors,
  });

  const toggleCollector = useMutation({
    mutationFn: (c: CollectorItem) => patchCollector(c.name, { enabled: !c.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeys.collectors() }),
  });

  // API keys
  const { data: keys = [] } = useQuery({
    queryKey: apiKeys.keyStatus(),
    queryFn: fetchKeyStatus,
  });

  return (
    <div className="h-full overflow-y-auto">
      <Header title="Настройки" subtitle="Источники и коллекторы" />

      <div className="max-w-2xl px-6 py-6 space-y-10">

        {/* ── Telegram channels ── */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-200 mb-1">📱 Telegram-каналы</h2>
          <p className="text-sm text-zinc-500 mb-4">
            Добавь каналы или конкретные темы для мониторинга. Для реального ингеста
            нужны API-ключи Telegram (в <code className="text-xs bg-zinc-800 px-1 rounded">.env</code>).
          </p>

          {/* Add form */}
          <div className="flex gap-2 mb-4">
            <Input
              placeholder="@канал или ссылка"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="flex-1"
            />
            <Input
              placeholder="тема (id, опц.)"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="w-32"
            />
            <Button
              onClick={() => channel.trim() && addMut.mutate()}
              disabled={!channel.trim() || addMut.isPending}
            >
              <Plus className="w-4 h-4" /> Добавить
            </Button>
          </div>

          {/* List */}
          {tg.length === 0 ? (
            <p className="text-sm text-zinc-600 italic">Каналы ещё не добавлены.</p>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
              {tg.map((s) => (
                <div key={s.id} className="flex items-center gap-3 px-4 py-2.5">
                  <Radio className="w-4 h-4 text-zinc-500 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-zinc-200 font-medium truncate">{s.name}</div>
                    <div className="text-xs text-zinc-500">
                      {s.config.topic_id ? `тема ${s.config.topic_id}` : "весь канал"}
                    </div>
                  </div>
                  <button
                    onClick={() => toggleMut.mutate(s)}
                    className={`text-xs px-2 py-1 rounded-md border transition-colors ${s.enabled
                      ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"
                      : "border-zinc-700 text-zinc-500"
                      }`}
                  >
                    {s.enabled ? "вкл" : "выкл"}
                  </button>
                  <button
                    onClick={() => delMut.mutate(s.id)}
                    className="text-zinc-600 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ── Collectors ── */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-200 mb-4">⚙️ Коллекторы</h2>
          {isLoading ? (
            <p className="text-sm text-zinc-600">Загрузка...</p>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
              {collectors.map((c) => (
                <div key={c.name} className="flex items-center gap-3 px-4 py-2.5">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass(c.dot)}`} />
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-zinc-300">{c.label}</span>
                    {c.mode === "stream" && (
                      <span className="ml-2 text-[10px] text-zinc-600 border border-zinc-700 px-1 rounded">VDS</span>
                    )}
                  </div>
                  {c.requires && c.key_present === false && (
                    <span className="text-[10px] text-amber-500/80 border border-amber-500/20 px-1.5 py-0.5 rounded">
                      нужен ключ
                    </span>
                  )}
                  <button
                    onClick={() => toggleCollector.mutate(c)}
                    className={`text-xs px-2 py-1 rounded-md border transition-colors ${c.enabled
                        ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"
                        : "border-zinc-700 text-zinc-500"
                      }`}
                  >
                    {c.enabled ? "вкл" : "выкл"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* ── API Keys ── */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-200 mb-4">🔑 Ключи API</h2>
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
            {keys.map((k) => (
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

        {/* ── Telegram notifications ── */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-200 mb-1">🔔 Telegram уведомления</h2>
          <p className="text-sm text-zinc-500 mb-4">
            Автоматическая рассылка свежих офферов в Telegram-чат после каждого запуска коллекторов.
          </p>

          {/* Status card */}
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
              <span>Свежие офферы с score ≥ 0.6, до 5 в час</span>
            </div>
          </div>

          {/* Setup instructions */}
          <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
            <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-3">
              Как настроить
            </p>
            <ol className="text-sm text-zinc-400 space-y-1.5 list-decimal list-inside mb-3">
              <li>
                Создай бота через{" "}
                <span className="text-zinc-300">@BotFather</span> и получи токен
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
    </div>
  );
}
