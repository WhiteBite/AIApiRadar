# AiApiRadar — кросс-платформенная архитектура (VDS / Cloudflare / CI)

Цель: один код хорошо работает и на долгоживущем VDS, и на Cloudflare
(Workers + D1), и в текущем гибриде (GitHub Actions + D1). Всё переключается
настройками, без форков логики.

---

## 1. Среды исполнения — их реально ТРИ, а не две

| | VDS / Docker | Cloudflare (Workers + D1) | GitHub Actions (текущий гибрид) |
|---|---|---|---|
| Процесс | долгоживущий | stateless, по Cron | разовый запуск по cron |
| Планировщик | APScheduler | Cron Triggers | GH `schedule:` |
| CPU/время | без лимита | жёсткий лимит (мс CPU) | 25 мин на job |
| Исходящие запросы | без лимита | subrequest cap (50 free / 1000 paid) | без лимита |
| БД | SQLite/Postgres | D1 (REST) | local SQLite → sync в D1 |
| Долгие соединения (ws) | да | нет | нет |
| Python-пайплайн | да | **нет** (нативно не крутится) | да |
| Frontend | FastAPI + Next | Pages/Workers + Next | Pages (read-only из D1) |

**Честная правда про Cloudflare:** Python-пайплайн (httpx/feedparser/bs4/
websocket) сегодня не исполняется на Workers нативно. Поэтому «cloudflare» =
**данные в D1 + статический фронт**, а пайплайн крутится либо в CI, либо в
контейнере (Container/VDS), который пишет в D1 через REST. Это надо принять как
данность и проектировать под неё, а не делать вид, что весь Python поедет в Worker.

---

## 2. Что сейчас НЕ переносится (точки напряжения)

1. **`web.py` завязан на SQLAlchemy** (`session_scope`, ORM-модели) — игнорирует
   `Database`-протокол. На D1 не работает вообще. → Единственный реальный разрыв
   в остальном чистой абстракции.
2. **certstream** — websocket-поток + буферы в памяти класса (`_buffer`, `_seen`).
   Живёт только на VDS. На stateless-средах невозможен.
3. **APScheduler** — длительный процесс. На CF/CI заменяется внешним cron'ом.
4. **discover.py / collect-once** — `asyncio.gather` с десятками исходящих probe.
   На VDS ок; на CF упрётся в subrequest cap и CPU.
5. **Состояние в памяти** (certstream `_seen`, дедуп) — теряется между запусками
   на stateless-средах.

---

## 3. Пять опор дизайна

### 3.1. Режим исполнения коллектора (poll vs stream)
Добавить в `core/collector.py` поле `mode`:
- `"poll"` — stateless, один проход `collect()` за вызов. Подходит **везде**
  (cron, CI, VDS). Это 14 из 15 коллекторов.
- `"stream"` — нужен долгоживущий процесс (certstream). **Только VDS.**

Раннер на каждой платформе активирует только совместимые коллекторы. Это
**ключевая** абстракция кросс-платформенности — одна строка метаданных решает,
где коллектор запускается.

```python
class Collector(abc.ABC):
    name: str = "base"
    kind: str = "generic"
    mode: str = "poll"        # "poll" | "stream"
    interval: int = 900
```

### 3.2. Абстракция Runner (как у БД — фабрика по платформе)
Сейчас планировщик один (APScheduler). Ввести протокол `Runner` и выбор по
`AIRADAR_PLATFORM`, как уже сделано для `Database`:

| Runner | Платформа | Поведение |
|--------|-----------|-----------|
| `ProcessRunner` | VDS | APScheduler; poll + **stream**; интервалы; фоновые job'ы (watchdog/discover/notify) |
| `BatchRunner` | CI / CF Cron | один проход всех `poll`-коллекторов → pipeline → enrich → score → notify; **без** stream; всё в рамках бюджета |

`BatchRunner` — это, по сути, нынешний `collect-once`, оформленный как явный
раннер. CF Cron Worker (JS) и GH Actions просто дёргают его.

### 3.3. Внешнее состояние + эквиваленты stream↔poll
Состояние не должно жить в памяти процесса:
- Дедуп/очередь discovery уже в БД (`domain_candidates`). ✅
- certstream `_seen` → при `stream`-режиме ок (процесс живёт); при `poll`-средах
  тот же домен-discovery даёт **`crtsh`** (опрашивает crt.sh, stateless).
  То есть: **VDS → certstream (stream), CF/CI → crtsh (poll)** закрывают одну и
  ту же задачу «новые домены». Это переключается режимом, логика общая.

### 3.4. Единый путь к БД (починить web.py)
Маршрутизировать **все** обращения к БД через `Database`-протокол, включая
read-запросы API. Тогда фронт-API работает и на SQLite (VDS), и на D1 (CF).
Варианты:
- (A) переписать запросы `web.py` на `Database.execute(...)` (SQL вместо ORM);
- (B) на CF фронт = Next.js, который ходит в отдельный read-API; этот API всё
  равно обязан уметь D1.

Рекомендация: **(A)** — один источник истины, меньше кода, полная переносимость.

### 3.5. RunBudget — бюджет на запуск (для serverless)
Передавать в pipeline/discovery бюджет:
```python
@dataclass
class RunBudget:
    max_subrequests: int | None = None   # None = безлимит (VDS)
    max_seconds: float | None = None
    max_probes: int = 40
```
На VDS — `None`/большие значения; на CF — жёсткие (≤45 subrequests, ≤N мс).
`discover.run_discovery(limit=...)` уже частично это делает — обобщить на все
исходящие.

---

## 4. Модель конфигурации — «всё в настройках»

Два уровня, с чётким приоритетом:

### 4.1. Статика — `Settings` (`config.py`, env / .env)
Платформа, ключи API, глобальные бюджеты, веса скоринга. Уже есть. Добавить:
```
AIRADAR_RUNNER=auto            # auto|process|batch (auto = по platform)
AIRADAR_ENABLE_DISCOVERY=true
AIRADAR_ENABLE_STREAMING=true  # игнорируется на не-VDS
AIRADAR_MAX_SUBREQUESTS=0      # 0 = безлимит
AIRADAR_PROBE_TIMEOUT=15
AIRADAR_DISCOVERY_LIMIT=40
```

### 4.2. Динамика — таблица `sources` (уже есть, но НЕ подключена!)
В БД есть таблица `sources(name, type, enabled, last_run, config)` и REST
`/api/sources`, но **раннер её не читает** — коллекторы жёстко берутся из
`load_builtin()`. Это и есть главный пробел «настраиваемости».

План: раннер при старте сверяет реестр коллекторов с `sources`:
- нет строки → создать с дефолтами (`enabled=1`, `interval=cls.interval`);
- `enabled=0` → не запускать;
- `config.interval` → переопределяет интервал;
- `config.*` → параметры коллектора (запросы, лимиты).

Тогда включение/выключение источника и смена интервала — через API/БД, **без
передеплоя**. Это закрывает требование «всё настраивается».

### Приоритет
`sources.config` (динамика, на лету) > `Settings` (env) > дефолты класса.

---

## 5. Рекомендуемые топологии деплоя

**VDS (всё-в-одном):** `ProcessRunner` + APScheduler + SQLite/Postgres +
FastAPI/uvicorn. certstream (stream) активен. Самый полный режим.

**Cloudflare:** D1 (хранилище) + Pages/Next (фронт) + read-API на `Database`.
Пайплайн — `BatchRunner` в контейнере/CI по расписанию, пишет в D1 через REST.
Stream-коллекторы выключены (`mode=stream` отсеивается). Discovery с жёстким
`RunBudget`.

**GitHub Actions (текущий гибрид):** `BatchRunner` ежечасно → local SQLite →
sync в D1 (wrangler). Уже работает; просто оформить как явный раннер.

---

## 6. Дорожная карта рефакторинга — ✅ ВЫПОЛНЕНО

1. ✅ **`sources` ↔ runner** — раннер читает enabled/interval/config из БД
   (`sched/source_config.py`). Источники включаются/настраиваются на лету.
2. ✅ **`Collector.mode` (poll/stream)** — поле на базовом классе; certstream =
   `stream`, остальные 14 = `poll`. Раннер фильтрует по совместимости.
3. ✅ **`Runner`-фабрика** (`ProcessRunner`/`BatchRunner`) — `sched.get_runner()`
   по `AIRADAR_RUNNER`/`platform`; `runtime.get_runner()` маршрутизирует CF в batch.
4. ✅ **`web.py` + `sources.py` на `Database`-протоколе** — raw SQL, без
   SQLAlchemy. Read-API и дашборд работают и на SQLite, и на D1.
5. ✅ **`RunBudget`** (`core/budget.py`) — `max_subrequests`/`max_seconds`/
   `max_probes`, протянут в `discover.run_discovery` и `batch_runner`.
6. ✅ **D1-путь** — `runtime.setup()` регистрирует `d1_db_factory` на CF;
   `init_db()` выполняет по одному statement (D1-safe), миграции через `ALTER`.
7. ✅ **crtsh TLD-harvest** — poll-эквивалент certstream: `%.ai/%.io/%.app/%.dev`
   с harvest-путём для brandable-доменов на serverless/CI.

### Осталось за рамками рефакторинга (отдельные задачи)
- **D1 init на деплое**: вызвать `init_db()` против D1 один раз при первом
  деплое (через CI-шаг или ручной прогон) — таблицы/индексы создаются по REST.
- **Реальный прогон batch на CF/CI**: проверить бюджеты subrequests на живой
  нагрузке и подобрать `AIRADAR_MAX_SUBREQUESTS`/`AIRADAR_DISCOVERY_LIMIT`.
- **Frontend → read-API на D1**: Next.js фронт уже ходит в JSON-API; убедиться,
  что на CF он указывает на инстанс с D1-бэкендом.

---

## 7. Итоговый принцип

Платформа выбирает **две фабрики** — `Database` и `Runner` — и **бюджет**.
Вся остальная логика (коллекторы, pipeline, enrich, discover, scorer) платформо-
независима и параметризуется через `sources` + `Settings`. Добавление платформы
= новая пара фабрик, а не форк бизнес-логики.
