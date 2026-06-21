# AiApiRadar — источники и стратегии обнаружения

Документ описывает: какие источники у нас **уже есть**, каких **не хватает**, и
какие **стратегии обнаружения** (discovery) позволяют находить сервисы, о
которых мы никогда не слышали — раньше, чем их перепостят Telegram-каналы.

Цель радара: детектить офферы бесплатного/триального доступа к AI API (free
credits, промокоды, free tier) **раньше** агрегаторов.

---

## 1. Архитектура обнаружения (как это работает)

Ключевой принцип: **discovery отделён от классификации**. Любой домен,
упомянутый где угодно в источниках, которые мы слушаем, становится кандидатом —
независимо от того, классифицировался ли сам пост как оффер.

```
коллекторы → нормализация → ХАРВЕСТ ДОМЕНОВ → prefilter → классификация → store
                                  │
                                  ▼
                          domain_candidates (очередь)
                                  │
                                  ▼
                    discover.py: probe (enrich) → promote
                                  │
                                  ▼
                          services (status='new') → scorer → фид
```

Компоненты:
- `pipeline/pipeline.py::_harvest_domains` — собирает домены (включая голые
  упоминания вида `zenmux.ai` без `http://`) **до** prefilter-дропа.
- Таблица `domain_candidates` — очередь кандидатов (`db/schema.sql`).
- `discover.py::run_discovery` — пробит кандидатов через `enrich.probe()`,
  промоутит только живые с AI-признаком + сигналом оффера.
- `sched/apscheduler_impl.py` — discovery-job каждые 20 минут.

---

## 2. Текущие источники (коллекторы)

Статус: ✅ работает · ⚠️ работает частично / требует настройки · ❌ заглушка

| Коллектор | Что собирает | Роль | Статус | Примечание |
|-----------|--------------|------|--------|------------|
| `huggingface` | релизы моделей key-orgs + статус Inference API | discovery + оффер | ✅ | починен: per-org запросы + детект `inference=warm` |
| `forum_rss` | nodeseek, linux.do, v2ex, hostloc, betalist, HN-фиды | discovery (харвест) | ✅ | эпицентр китайской 中转站-сцены |
| `hackernews` | Show HN / новые посты | discovery (харвест) | ✅ | |
| `reddit` | сабреддиты | discovery (харвест) | ✅ | |
| `producthunt` | RSS новых запусков | discovery (харвест) | ✅ | |
| `directories` | theresanaiforthat, futurepedia, toolify, betalist, uneed, peerlist, launched, lablab, devpost | discovery | ✅ | расширен лонч-агрегаторами и хакатон-платформами |
| `github` | поиск репозиториев + **code search** (`github_code`) | discovery | ✅ | ищет `base_url=` в коде |
| `github_lists` | README известных + **самонаходимых** awesome-репо | discovery | ✅ | сам ищет свежие списки |
| `searchdorks` | Google CSE по дорками | discovery | ⚠️ | нужен `AIRADAR_SEARCH_API_KEY` + `_CX` |
| `certstream` | новые домены из CT-логов | discovery | ✅ | keyword + TLD-harvest `.ai/.io/.app/.dev` (stream, VDS) |
| `crtsh` | новые домены через crt.sh | discovery | ✅ | poll-паритет certstream для serverless |
| `twitter` | v2 API search + Nitter fallback | discovery | ⚠️ | нужен `AIRADAR_TW_BEARER_TOKEN` |
| `youtube` | видео/описания, 17 мультиязычных запросов | discovery (харвест) | ✅ | харвест ссылок из описаний |
| `openrouter` | каталог моделей/провайдеров | discovery | ✅ | публичный, без ключа |
| `packages` | новые AI-SDK на npm + PyPI | discovery | ✅ | публичные реестры |
| `fofa` | relay-панели по favicon-hash | discovery | 🧩 | нужен `AIRADAR_FOFA_KEY` + реальные хэши |
| `telegram` | агрегатор-каналы + forward-chain | замер lead-time + upstream-discovery | ✅ | surface upstream-каналов |
| `coupon` | AppSumo/SaaSWorthy/Futurelist/Uneed | discovery | ✅ | переписан под агрегаторы |

### Сквозной механизм поверх всех текстовых коллекторов
**Mention/domain harvesting** — каждый текст из любого коллектора выше
сканируется на упоминания доменов (URL и голые), новые идут в `domain_candidates`.
Это превращает все коллекторы в источники discovery. ✅ Построено.

---

## 3. Источники, которых не хватает (ранжир по отдаче)

| # | Источник / механизм | Что находит | Стоимость | Переиспользует |
|---|---------------------|-------------|-----------|----------------|
| 1 | **GitHub code search** по `base_url` | релеи, гейтвеи, новые провайдеры | средняя | `github.py` + probe |
| 2 | **certstream → probe для `.ai`/`.io`** | brandable-домены в день регистрации | низкая | probe-воркер |
| 3 | **Link-graph** от промоученных | соседи / провайдеры / конкуренты | средняя | `enrich` + harvest |
| 4 | **Динамические awesome-list'ы** | кураторские таблицы релеев | низкая | `github_lists.py` |
| 5 | **OpenRouter / каталоги моделей** | новые провайдеры структурно | низкая | новый мини-коллектор |
| 6 | **npm / PyPI** новые AI-SDK | сервис по его SDK-пакету | средняя | новый коллектор |
| 7 | **Telegram forward-chain** | upstream-каналы экосистемы | средняя | `telegram.py` |
| 8 | **Newsletters** (TLDR AI, Ben's Bites) | кураторские daily-списки | низкая | новый RSS/email |
| 9 | **AlternativeTo / G2 / SaaSWorthy** | «alternatives to X» — новые игроки | средняя | `directories` |
| 10 | **Discord** (абуз/AI-серверы) | сцена раздач до форумов | высокая | новый коллектор (бот) |
| 11 | **App stores** (Chrome Web Store) | новые AI-расширения/приложения | средняя | новый коллектор |
| 12 | **coupon-агрегаторы** (AppSumo и т.п.) | лимитированные промо известных сервисов | средняя | переписать `coupon.py` |

---

## 4. Стратегии обнаружения (детально)

### 4.1. GitHub code search по `base_url` 🔴 высший приоритет
Каждый релей и новый провайдер рано или поздно попадает в чей-то пример кода:
```python
base_url="https://api.zenmux.ai/v1"
OPENAI_API_BASE="https://some-new-gateway.com/v1"
```
Сейчас `github.py` использует `search/repositories`. Нужен `search/code` по
паттернам `"/v1/chat/completions"`, `base_url=`, `OPENAI_API_BASE` с отсевом
официальных хостов (openai.com, anthropic.com, ...). Извлекаем host → кандидат →
probe. Особенно вскрывает китайскую 中转站-сцену и новые гейтвеи, которых нет в
текстах нигде. Требует GitHub-токена (code search требует авторизации).

### 4.2. certstream → очередь кандидатов для `.ai` 🔴 высший приоритет ▶️ in progress (Agent A)
Сейчас `domain_matches()` пропускает только домены с ключевиком в имени, поэтому
`zenmux`/`getmerlin`/`band` невидимы. Меняем подход: **все новые `.ai`-домены**
(объём управляемый, почти все — AI-продукты) кладём в `domain_candidates` и
пробим. Ловит сервис в день выпуска TLS-сертификата — **раньше любого упоминания**.
Keyword-путь оставляем для прочих TLD. Идеальная синергия с probe-воркером.

### 4.3. Link-graph от промоученных сервисов 🟡
Когда discovery промоутит сервис — заходим на его `/models`, `/providers`,
страницы «alternatives» и собираем **другие** домены оттуда. AI-гейтвеи
перечисляют провайдеров, которых роутят, и ссылаются на конкурентов. Каждый
промоут порождает новых кандидатов — сеть расширяется сама.

### 4.4. Динамические awesome-list'ы 🟡
`github_lists.py` харвестит README из захардкоженного списка репо. Добавить шаг:
искать на GitHub репо по `free-llm-api` / `awesome ai api` / `中转站`,
сортировать по `updated`, авто-добавлять новые в набор для харвеста README.
Самораширяющиеся кураторские списки.

### 4.5. OpenRouter / каталоги моделей 🟡
Поллим `OpenRouter /api/v1/models` (и аналоги гейтвеев); новый slug провайдера =
новый сервис. Структурно, почти без шума.

### 4.6. Реестры пакетов (npm / PyPI) 🟢
Сервис выпускает SDK: `zenmux`, `@getmerlin/sdk`. Поиск по реестрам, сортировка
по дате, фильтр по ai/llm-ключевикам → поле homepage → кандидат.

### 4.7. Telegram forward-chain (upstream-discovery) 🟢
Сообщения несут `forward_from_chat`. Харвестим, из каких каналов агрегаторы
форвардят → авто-подписка на upstream → находим **источники**, кормящие всю
экосистему, а не только релеи.

### 4.8. Backward source attribution (scoreboard) 🟢
Через `lead_metrics` ранжируем источники по lead-time и реинвестируем бюджет
краулинга в самые ранние. Это оптимизация, не новый discovery.

---

## 5. Воронка покрытия (по времени появления)

```
certstream .ai        → ловит в момент рождения домена     (T − дни)
github code search    → ловит когда кто-то закодил          (T − часы/дни)
mention harvest ✅    → ловит когда кто-то упомянул          (T + часы)
link-graph            → ловит соседей уже найденного         (компаундит)
telegram (агрегаторы) → замер: насколько мы опередили        (T + дни)
```

### Известные слепые зоны
1. Домен **нигде не упомянут** в наших источниках и не `.ai` → не найдём.
   Зрение = сумма коллекторов.
2. Оффер **только на главной**, пустой `/pricing` → probe не находил триггеров.
   ✅ Частично закрыто — relay-эндпоинты `/api/status`, `/v1/models`, `/api/notice` теперь пробиваются (см. §8.3). Закрывает случаи, когда панель жива, но `/pricing` пуст.
3. **Промокоды** discovery не извлекает — только сам сайт. За коды отвечает
   prefilter + классификатор по тексту поста.
4. Детектор моделей в `enrich.py` — **по подстроке** → ложные срабатывания
   (`asp.net` ← подстрока «gpt»). Нужен word-boundary матчинг.

---

## 6. Дорожная карта — статус

Статус: ✅ сделано · 🧩 структурно готово (нужен ключ/ops) · ⏳ не начато

1. ✅ **Relay-эндпоинты в `enrich.probe`** (§8.3) — `/api/status`, `/v1/models`, `/api/notice`.
2. ✅ **certstream → probe для `.ai/.io/.app/.dev`** (§4.2) + **crtsh** poll-паритет (§7).
3. ✅ **GitHub code search** по `base_url` (§4.1) — `github_code`.
4. ✅ **Многоязычные видео/соц-площадки** (§9) — YouTube (17 запросов) + RSSHub-маршруты.
5. ✅ **Link-graph** от промоученных (§4.3) — `first_source='linkgraph'`.
6. ✅ **Динамические awesome-list'ы** (§4.4) — github_lists сам ищет свежие репо.
7. ✅ **OpenRouter каталог** (§4.5) + **npm/PyPI** новые AI-SDK (§4.6).
8. ✅ **Telegram forward-chain** (§4.7) — surface upstream-каналов для ревью.
9. ✅ **Каскад языков** (§8.6) — early-signal буст в скоринге (zh/ru без en → +0.1).
10. ✅ **word-boundary** в детекторе моделей `enrich.py` (слепая зона §5.4).
11. ✅ **coupon.py** переписан под агрегаторы (AppSumo/SaaSWorthy/Futurelist/Uneed).
12. 🧩 **favicon-hash FOFA** (§8.1) — коллектор готов, но нужен `AIRADAR_FOFA_KEY` + реальные mmh3-хэши панелей (placeholder'ы в `RELAY_FAVICON_HASHES`).

### Осталось (отдельные задачи / нужен внешний ресурс)
- ⏳ **Zone-файлы CZDS** для `.app`/`.dev` (§8.2) — нужна заявка-одобрение реестра.
- 🧩 **RSSHub self-host** (§8.5) — маршруты добавлены, свой инстанс = ops.
- ⏳ **GitHub issues relay-движков** (§8.4) — code search есть, issues-харвест нет.
- ⏳ **Leak-мониторинг** gists/Pastebin (§8.4) — только домены, со строгими гардрейлами.
- ⏳ **Backward source-attribution** scoreboard через `lead_metrics` (§4.8).

---

## 7. Конфигурация (ключи для частичных источников)

| Переменная | Включает |
|------------|----------|
| `AIRADAR_SEARCH_API_KEY` + `AIRADAR_SEARCH_CX` | `searchdorks` (Google CSE) |
| `AIRADAR_TW_BEARER_TOKEN` | `twitter` keyword-search (иначе только Nitter fallback) |
| `AIRADAR_TG_API_ID` + `_HASH` | `telegram` ingest (Telethon) |
| GitHub token | code search (§4.1), повышенные лимиты `github` |

---

## 8. Инфраструктурный слой (TIER S) — молчаливый длинный хвост

Главный пробел v1: мы находим только то, о чём **уже написали**. Но огромная
часть 中转站 никогда не попадает ни в один форум — оператор поднял new-api панель,
набрал юзеров через WeChat и живёт. Их видно **только по инфраструктуре**.

```
Матрица покрытия по времени:
zone file .app/.dev      §8.2   ← рождение домена (T − дни)
favicon FOFA/Shodan      §8.1   ← деплой панели   (T − часы)
github code/leak         §8.4   ← кто-то закодил
CSDN/Bilibili туториал   §9     ← день обнаружения
mention harvest ✅              ← упоминание       (T + часы)
TG-агрегаторы ✅                ← хвост (мы их опережаем)
```

### 8.1. Favicon-hash по FOFA/Shodan/Censys 🔴
95% релеев работают на new-api / one-api / sub2api / CLIProxyAPI — у каждого
одинаковый favicon. Считаем mmh3-хэш иконки известного релея → ищем по нему
(`icon_hash=` в FOFA, `http.favicon.hash:` в Shodan) → находим панели, живые, но
нигде не упомянутые. Новый ортогональный слой, **самый мощный**.
**Цена/риск:** FOFA/Shodan/Censys платные или с жёстким free-лимитом — нужен
бюджет. Вежливый rate-limit при пробе найденных хостов.

### 8.2. Zone-файлы через ICANN CZDS 🟡
Бесплатный ежедневный полный список доменов в gTLD. **Важно:** CZDS отдаёт
только **gTLD** (`.app`, `.dev` — Google Registry — есть). `.ai` (Ангилья) и
`.io` — это **ccTLD, их в CZDS НЕТ**. Поэтому zone-файлы **дополняют** certstream
для `.app`/`.dev`, но для `.ai` остаётся CT-логи (certstream). Доступ — заявка на
каждый TLD с ручным одобрением реестра. Инструменты: pyCZDS, czdsdump.

### 8.3. Стандартные эндпоинты релеев ✅ СДЕЛАНО
new-api/one-api отдают `GET /api/status` (версия = fingerprint),
`GET /v1/models` (список моделей = сигнал оффера), `GET /api/notice` (часто
текст «注册即送 $X»). Встроено в `enrich.probe` — закрывает слепую зону §5.2
(пустой `/pricing`). Все анонимные GET, проба только когда `/pricing` не дал
богатого оффера.

### 8.4. Утечки/активность на GitHub 🟡
- **Code search** по `base_url="https://.../v1"`, `OPENAI_API_BASE` с отсевом
  официальных хостов → host релея → кандидат (§4.1).
- **Issues relay-движков**: операторы вставляют URL своих деплоев в issues
  new-api/one-api с просьбой о помощи — прямой сбор доменов. Рост stars/forks =
  волна новых операторов.
- **Утечки конфигов** (gists/.env/Pastebin): рабочий `base_url` + `sk-` = сервис
  точно жив. 🚨 **Гардрейл:** извлекаем ТОЛЬКО домен; ключ `sk-` немедленно
  отбрасывается, никогда не пишется в БД и не используется. Иначе это харвестинг
  краденых кредов.

### 8.5. RSSHub 🟡
5000+ RSS-маршрутов одним деплоем: zhihu, bilibili, weibo, xiaohongshu, juejin,
CSDN, telegram-каналы. Драматически расширяет `forum_rss` на китайскую сцену
(см. §9). Минус — ops-нагрузка (свой деплой, китайские маршруты часто лочат).

### 8.6. Предиктивные сигналы 🟢
- **Каскад языков**: релей идёт zh (T+0) → ru (T+1–3д) → en Reddit (T+3–7д).
  Есть в китайском, но ещё нет в английском → метка `early_signal` + буст. Это
  делает нас источником для ТГ-агрегаторов.
- **Дельта моделей**: вышел новый Opus/GPT — кто первым отдаёт его через
  `/v1/models`? Новый хост с премиум-моделью = новый релей.

---

## 9. Многоязычные видео / соц-площадки

Туториалы «как получить бесплатный API» выходят на региональных площадках на
местном языке **в день обнаружения релея, часто раньше промо-постов**. Ловим их
поиском по локализованным ключевикам за последние сутки и харвестим ссылки.

### Площадки по регионам
| Регион | Площадки |
|--------|----------|
| Китай | Bilibili, Zhihu, Xiaohongshu, Douyin, CSDN, Juejin |
| Корея | Naver Blog, Tistory, Velog, YouTube KR |
| Вьетнам | YouTube, Viblo, Facebook-группы |
| Индия | YouTube, Medium, Telegram |
| Глобально | YouTube, TikTok |

### Механизм
```
локализованный запрос + publishedAfter=24h
   → заголовки / описания / (комменты)
   → харвест ссылок и голых доменов
   → domain_candidates → probe → promote
```
Локализованные ключевики: `免费API`, `无需信用卡`, `무료 API`, `API miễn phí`,
`मुफ्त API`, `free API key`, `бесплатный API`.

### Реализация
- **YouTube**: расширить `youtube.py` — `search` с `q` + `publishedAfter`,
  мультиязычный набор запросов, харвест ссылок из описаний.
- **Китайские письменные площадки**: гнать через **RSSHub** (§8.5), а не писать
  N скрейперов.
- Общий набор `MULTILINGUAL_QUERIES` переиспользуют `youtube`, `searchdorks`, RSSHub.

### Нюансы (честно)
- YouTube Data API: квота 10k юнитов/день, поиск = 100 юнитов → ~100 запросов/сутки.
- Бóльшая часть не-YouTube площадок требует RSSHub или скрейпинга.
- Комменты — золото, но дорого/лимитировано; начинать с заголовков+описаний.
- Шум фильтрует probe + классификатор на выходе.

---

## 10. Architecture notes

### Domain harvest pipeline

```
signal text
    │
    ▼  _HARVEST_HINT_RE: AI/offer context gate
    ▼  _BARE_DOMAIN_RE: bare-domain extract (≥3-char labels, TLD allow-list, no emails)
    ▼  + URL-extracted domains from normalize.normalize()
    │
    ▼  is_blocked_domain / registrable_domain filter
    │
    ▼
domain_candidates  ← priority='high' if offer trigger within 100 chars of domain
    │
    ▼  discover.run_discovery(): ORDER BY high first, then first_seen ASC
    ▼  enrich.probe() → should_promote()
    │
    ▼
services (status='new') → scorer → фид
```

### `priority='high'` fast-lane in the probe queue

При харвесте каждый домен получает `priority` в зависимости от контекста: если
рядом (в пределах 100 символов) найдено ключевое слово оффера (free, trial,
credits, $, 注册送, кредит и др.) — `priority='high'`, иначе `'normal'`. Очередь
`run_discovery` выбирает `high` первыми (`ORDER BY CASE WHEN priority='high' THEN 0
ELSE 1 END, first_seen ASC`), что сокращает время до промоута для самых горячих
сигналов. Если домен уже в очереди, а новое упоминание дало `high` — строка
апгрейдится (`UPDATE ... SET priority='high' WHERE priority!='high'`).

### Rate-limiting policy для probe-воркера

| Параметр | Значение | Комментарий |
|----------|----------|-------------|
| Конкурентность | `Semaphore(8)` | ≤8 одновременных probe |
| Таймаут на запрос | 15 с (`timeout=15.0`) | увеличен с 10 с — панели в Азии бывают медленными |
| Retry backoff | `[1 ч, 6 ч, 24 ч]` | экспоненциальная задержка по числу неудачных попыток |
| Max attempts | 3 (по умолчанию) | после 3-х неудач домен перестаёт выбираться |

Retry-логика: перед пробом проверяется `attempts` и `probed_at`; если с момента
последнего пробa прошло меньше минимума — домен пропускается (`stats["skipped"]`).

### Word-boundary note для детектора моделей

`enrich.detect_models()` использует поиск по подстроке (`kw in blob`).
Известный false positive: `asp.net` содержит `gpt` как подстроку.
Relay-путь (`/v1/models` → model IDs) этой проблемы не имеет, т.к. ID моделей —
структурированные строки. Word-boundary исправление в `detect_models` — в плане
(§6.7 дорожной карты).

### SSRF guard для приватных IP

`discover._safe_to_probe()` отклоняет loopback, `.local`, `.internal`, `.lan`,
`.localdomain` и голые IPv4-литералы до любого HTTP-запроса. Приватные диапазоны
RFC-1918 дополнительно закрываются на уровне ОС — defence-in-depth поверх guard'а.
