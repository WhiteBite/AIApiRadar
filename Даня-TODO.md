# Даня — что нужно дать радару

Всё бесплатно. Регистрации без карты. Без ключей радар уже работает —
но с ключами он видит в 3-4 раза больше источников.

---

## 1. GitHub token — 2 минуты, самый жирный выигрыш

**Где взять:**
1. github.com → профиль → Settings → Developer settings
2. Personal access tokens → Tokens (classic) → Generate new token
3. Срок: 90 дней или без срока. **Никаких scopes не нужно** — просто создать.

**Вставить в `.env`:**
```
AIRADAR_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

**Что включит:**
- GitHub code search: ищет `base_url="https://api.newrelay.ai/v1"` в чужом коде →
  находит новые релеи до того, как кто-то их упомянул
- Лимит запросов: 60/час → 5000/час
- Awesome-list поиск: `github_lists` сам находит свежие таблицы relay-сайтов

**Хватит ли?** Да. 5000 запросов/час более чем достаточно для нашего ритма.

---

## 2. Telegram api_id + api_hash — 5 минут, второй по важности

**Где взять:**
1. Открыть my.telegram.org в браузере (войти по номеру телефона)
2. «API development tools» → создать приложение
3. Скопировать `App api_id` и `App api_hash`

**Вставить в `.env`:**
```
AIRADAR_TG_API_ID=12345678
AIRADAR_TG_API_HASH=abcdef1234567890abcdef1234567890
```

⚠️ Первый запуск попросит авторизоваться в терминале (введёшь код из Telegram).
После этого сессия сохраняется и больше не спрашивает.

**Что включит:**
- Мониторинг каналов из списка `CHANNELS` в `telegram.py` в реальном времени
- Автонаходимость upstream-каналов: когда агрегатор форвардит пост — мы видим
  ОТКУДА он взял и можем подписаться на первоисточник
- Замер lead-time: насколько мы опережаем TG-агрегаторы

**Хватит ли?** Да. Но надо будет вручную добавлять каналы, которые хочешь
мониторить (через `/api/sources`). Текущий список в коде — стартовая точка.

---

## 3. YouTube API key — 10 минут, хорошая добавка

**Где взять:**
1. console.cloud.google.com → создать проект (или взять существующий)
2. APIs & Services → Enable APIs → найти "YouTube Data API v3" → Enable
3. APIs & Services → Credentials → Create Credentials → API key

**Вставить в `.env`:**
```
AIRADAR_YOUTUBE_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxxxx
```

**Что включит:**
- 17 запросов на разных языках за последние 24 часа:
  китайский (`免费API`, `中转站`), русский, корейский, вьетнамский, хинди, японский, английский
- Харвест ссылок из описаний видео → домены в discovery-очередь
- Ловит туториалы «как получить бесплатный API» в день их выхода

**Хватит ли?** Квота 10 000 юнитов/день, один поиск = 100 юнитов → 100 запросов.
У нас 17 запросов каждые 6 часов = 68/день. Запас есть.

---

## 4. Google Custom Search — 15 минут, добавка для search dorks

**Где взять:**
1. programmablesearchengine.google.com → «Add» → Name что угодно,
   выбрать «Search the entire web» → Create
2. Скопировать **Search engine ID** (это `cx`)
3. console.cloud.google.com → APIs & Services → Custom Search API → Enable
4. Credentials → API key (тот же проект что у YouTube или новый)

**Вставить в `.env`:**
```
AIRADAR_SEARCH_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxxxx
AIRADAR_SEARCH_CX=xxxxxxxxxxxxxxx
```

**Что включит:**
- `searchdorks`: Google-поиск по дорками с `dateRestrict=d1` (только за сутки)
- Запросы вида: `"promo code" AI API free`, `(site:*.ai) "free trial" launch`
- Ловит страницы которые Google проиндексировал за последние 24 часа

**Хватит ли?** Бесплатная квота — 100 запросов/день. У нас 15 дорков ×
4 запуска в сутки = 60. Вписывается. Если нужно больше — $5 за 1000 доп. запросов.

---

## Итоговая таблица

| Ключ | Время | Что включает | Хватит? |
|------|-------|--------------|---------|
| GitHub token | 2 мин | code search, 5000/час | ✅ с запасом |
| Telegram api | 5 мин | мониторинг каналов, upstream discovery | ✅ да |
| YouTube API | 10 мин | 17 мультиязычных запросов/день | ✅ с запасом |
| Google CSE | 15 мин | 60 search dorks/день | ✅ еле-еле (100 лимит) |

**Суммарно:** ~30 минут на всё.

---

## Что НЕ нужно (и почему)

- **FOFA** — платный ($), нужны ещё вручную посчитанные mmh3-хэши favicon.
  Отдача большая, но не для старта.
- **Twitter/X** — можно получить бесплатно, но заявка проходит модерацию
  (дни), и лимиты на Free tier жёсткие. Nitter-fallback уже работает.
- **RSSHub self-host** — это не ключ, а свой сервер. Публичный rsshub.app
  уже подключён, но может тормозить. Нужен когда вырастешь.
- **CZDS zone-файлы** — заявка на icann.org, реестр одобряет вручную.
  certstream и crtsh уже закрывают `.ai`-домены.

---

## Без ключей уже работает

`forum_rss` · `hackernews` · `reddit` · `producthunt` · `directories`
· `crtsh` · `certstream` · `huggingface` · `coupon` · `openrouter`
· `packages` · весь discovery-движок (харвест → probe → промоут)

Радар уже видит релеи и промокоды. Ключи расширяют охват,
но не являются условием запуска.
