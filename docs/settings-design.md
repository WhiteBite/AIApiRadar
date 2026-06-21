# Настройки — дизайн нормальной конфигурации

Цель: всё, что сейчас зашито в код (ключевые слова, запросы, фиды, лимиты) или
показано фейково (список коллекторов), должно настраиваться из UI, без редеплоя.
Бэкенд для этого почти готов — не хватает связки и пары эндпоинтов.

---

## 1. Что не так сейчас

| Проблема | Где | Факт |
|----------|-----|------|
| Список коллекторов захардкожен | `frontend/app/settings/page.tsx` (`BUILTIN`) | 9 статичных строк, реально 19 коллекторов |
| Нет тогглов вкл/выкл | там же | бейдж «активен» — просто текст |
| `sources.config` не читается коллекторами | все collectors | enable/disable + interval раннер читает, но queries/feeds — нет |
| Ключевые слова в коде | `prefilter.py`, `searchdorks.py`, `youtube.py`, `github.py`, `forum_rss.py` | менять только кодом |
| Нет реестр-эндпоинта | `web.py` | фронт не знает что реально существует и какой статус |
| Нет статуса ключей | — | не видно какие API-ключи выставлены и что включают |

**Важно:** таблица `sources(name,type,enabled,last_run,config)`, CRUD
`/api/sources`, `source_config.py` (enabled/interval/config) — **уже работают**.
Telegram-каналы их используют. Нужно дотянуть это до коллекторов и ключевиков.

---

## 2. Модель конфигурации (3 уровня)

```
дефолты в коде (fallback)  <  app_settings (глобальное)  <  sources.config (на коллектор)
```

1. **Дефолты класса** — то что сейчас в модулях, остаётся как fallback.
2. **`sources.config`** (на коллектор) — `enabled`, `interval`, и
   collector-specific списки: `queries`, `feeds`, `repos`, `tlds`.
3. **`app_settings`** (новая таблица key→JSON) — глобальное: keyword-списки
   prefilter, discovery-лимиты, веса скоринга, notify-порог, RSSHub URL.

---

## 3. Бэкенд — что добавить

### 3.1. Метаданные коллектора (база)
В `core/collector.py` добавить декларативные поля:
```python
class Collector:
    requires: str | None = None        # env-ключ, без которого не работает (или None)
    config_keys: dict[str, type] = {}  # редактируемые ключи config + тип (list/int/str)
```
Примеры: `youtube.requires = "AIRADAR_YOUTUBE_API_KEY"`,
`youtube.config_keys = {"queries": list}`; `fofa.requires = "AIRADAR_FOFA_KEY"`;
`searchdorks.config_keys = {"dorks": list}`.

### 3.2. `GET /api/collectors` — реальный реестр
Мержит registry + `sources` + наличие ключа:
```json
[{
  "name": "youtube", "kind": "api", "mode": "poll",
  "enabled": true, "interval": 3600, "last_run": "2026-06-21T...",
  "requires": "AIRADAR_YOUTUBE_API_KEY", "key_present": false,
  "config_keys": {"queries": "list"},
  "config": {"queries": ["免费API", "..."]}   // текущее (override или дефолт)
}]
```
`PATCH /api/collectors/{name}` — `{enabled?, interval?, config?}` → пишет в `sources`.

### 3.3. Коллекторы читают config (с fallback)
Паттерн в каждом настраиваемом коллекторе:
```python
from ..sched.source_config import get_source_config
cfg = get_source_config(self.name)["config"]
self.queries = cfg.get("queries") or DEFAULT_QUERIES
```
Применить к: `youtube` (queries), `searchdorks` (dorks), `github`
(queries/code_queries/issues), `forum_rss` (feeds), `packages` (npm_keywords),
`github_lists` (repos), `fofa` (hashes), `twitter` (queries/accounts).

### 3.4. Prefilter из `app_settings` (с fallback)
`prefilter.match()` грузит списки из `app_settings["prefilter"]`, если есть,
иначе дефолты в коде. Ключи: `zh_strong, zh_weak, ru, en_strong, en_weak`.
Кешировать в памяти, инвалидировать при PUT.

### 3.5. `GET/PUT /api/settings` — глобальные тумблеры
`app_settings` (key TEXT PK, value JSON). Эндпоинт отдаёт/пишет:
prefilter-списки, discovery (`limit`, `probe_timeout`, harvest TLDs),
score weights, `notify_min_score`, `rsshub_url`.

### 3.6. `GET /api/keys` — статус ключей (без значений!)
По метаданным коллекторов: `[{key, present:bool, unlocks:[collectors]}]`.
НИКОГДА не отдавать значения — только present/absent.

---

## 4. Фронтенд — редизайн в табы

Сейчас одна простыня. Разбить на табы внутри `/settings`:

### Таб 1 — Источники
- Реальный список из `/api/collectors`: тоггл вкл/выкл, поле interval,
  бейдж режима (poll/stream), бейдж «нужен ключ» (серый/выкл если ключа нет).
- Разворот строки → редактор `config` (queries/feeds как chips: добавить/удалить).
- Telegram-каналы — отдельной под-секцией (как сейчас, уже работает).

### Таб 2 — Ключевые слова
- Мультиязычные списки prefilter (ZH strong/weak, RU, EN strong/weak) — chips
  с add/remove, кнопка «сбросить к дефолтам».
- Живой превью: вставил текст → видно проходит ли prefilter и какие слова сматчили
  (через `POST /api/prefilter/test`).

### Таб 3 — Discovery
- `discovery_limit`, `probe_timeout`, harvest TLDs, budget-капы (subrequests).

### Таб 4 — Ключи API
- Из `/api/keys`: что выставлено (✓/✗), что каждый ключ включает.
- Инструкция куда вписать (`.env` для VDS, GitHub Secrets для CI).

### Таб 5 — Уведомления
- `notify_min_score`, rate. Текущая инфа про GitHub Secrets / `.env`.

---

## 5. Фазы внедрения (по отдаче/риску)

1. **Фаза 1 — реальные источники.** `GET /api/collectors` + `PATCH` + переписать
   таб «Источники» на живые данные с тогглами/interval. Бэкенд на 90% готов
   (`sources` + `source_config`). Убирает главный обман (фейковый `BUILTIN`).
2. **Фаза 2 — config коллекторов.** Коллекторы читают queries/feeds из
   `sources.config`; UI-редактор списков в разворачивающейся строке.
3. **Фаза 3 — ключевые слова.** `app_settings` + prefilter из БД + таб «Ключевые
   слова» с превью.
4. **Фаза 4 — глобальные настройки + статус ключей.** `/api/settings`,
   `/api/keys`, табы Discovery / Ключи API.

---

## 6. Принцип

Один источник правды на каждый параметр, с явным приоритетом
(код < глобальное < на-коллектор). UI читает реестр и метаданные, а не
хардкодит списки. Добавил коллектор в Python → он сам появляется в UI с
правильным статусом и нужным ключом.
