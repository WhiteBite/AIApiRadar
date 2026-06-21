"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Radio } from "lucide-react";

import { fetchSources, createSource, updateSource, deleteSource, apiKeys } from "@/lib/api";
import type { SourceItem } from "@/lib/types";
import { Header } from "@/components/layout/header";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const BUILTIN = [
  { key: "certstream", label: "CertStream (CT-логи)", dot: "bg-cyan-400" },
  { key: "forum_rss", label: "Форумы (nodeseek / linux.do / v2ex)", dot: "bg-orange-400" },
  { key: "crtsh", label: "crt.sh (новые домены)", dot: "bg-cyan-400" },
  { key: "github", label: "GitHub", dot: "bg-zinc-400" },
  { key: "huggingface", label: "HuggingFace (релизы моделей)", dot: "bg-yellow-400" },
  { key: "producthunt", label: "Product Hunt", dot: "bg-red-400" },
  { key: "directories", label: "AI-каталоги", dot: "bg-lime-400" },
  { key: "coupon", label: "Купоны / аффилиаты", dot: "bg-purple-400" },
  { key: "youtube", label: "YouTube", dot: "bg-red-400" },
];

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
                    className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                      s.enabled
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

        {/* ── Built-in collectors ── */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-200 mb-4">⚙️ Встроенные коллекторы</h2>
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
            {BUILTIN.map((c) => (
              <div key={c.key} className="flex items-center gap-3 px-4 py-2.5">
                <span className={`w-2 h-2 rounded-full shrink-0 ${c.dot}`} />
                <span className="flex-1 text-sm text-zinc-300">{c.label}</span>
                <span className="text-xs text-emerald-400">активен</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-zinc-600 mt-2">
            Коллекторы запускаются по расписанию командой{" "}
            <code className="bg-zinc-800 px-1 rounded">aiapiradar run</code>.
          </p>
        </section>
      </div>
    </div>
  );
}
