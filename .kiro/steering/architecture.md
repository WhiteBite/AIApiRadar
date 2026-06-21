---
inclusion: always
---

# Архитектура AiApiRadar — читать перед любыми изменениями

## Что запущено на продакшне

```
aiapiradar.cf.whitebite.ru (Cloudflare)
├── worker/src/index.ts      ← TypeScript (Hono), ЭТО и есть API на сайте
│   Эндпоинты: /api/offers /api/services/:id /api/stats /api/analytics
│   Читает данные из Cloudflare D1 напрямую
│
├── frontend/                ← Next.js, деплоится на Cloudflare Pages
│   Вызывает worker через NEXT_PUBLIC_API_URL
│
└── Cloudflare D1             ← БД (SQLite-совместимая)
```

## Что НЕ деплоится

```
aiapiradar/web.py            ← FastAPI, ТОЛЬКО для локальной разработки (VDS)
                               Изменения здесь НЕ влияют на сайт
```

## Где что лежит

| Задача | Файл |
|--------|------|
| **Добавить API эндпоинт на сайт** | `worker/src/index.ts` |
| Локальный API / VDS | `aiapiradar/web.py` |
| Сбор данных (CI/CD) | `aiapiradar/collectors/`, `aiapiradar/pipeline/` |
| Планировщик CI | `.github/workflows/collectors.yml` |
| Деплой воркера и фронта | `.github/workflows/deploy.yml` |
| Схема D1 | `aiapiradar/db/schema.sql` |

## Цикл данных

```
GitHub Actions (hourly)
  └── Python pipeline (collectors → pipeline → D1 через wrangler)
        └── Cloudflare D1 (данные обновились)
              └── Worker читает D1 → отдаёт фронту
```

## Ключевое правило

**Если нужно что-то показать на сайте — меняй `worker/src/index.ts`.**
`web.py` существует как зеркало для локального запуска и VDS-деплоя.
Они должны быть синхронизированы, но приоритет для сайта — воркер.
