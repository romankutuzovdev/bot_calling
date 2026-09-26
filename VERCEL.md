# Деплой фронта на Vercel (бэкенд на сервере)

Схема: браузер → **Vercel (UI + HTTPS)** → proxy `/api/*` → **`http://91.149.133.54:8080`**.

Ollama / ElevenLabs остаются на Windows Server.

## 1. Сервер (бэкенд)

Бот должен слушать `0.0.0.0:8080`, порт 8080 проброшен на `192.168.0.115`.

Проверка с интернета:
```bash
curl http://91.149.133.54:8080/api/health
```
Если timeout — Vercel UI откроется, API будет **502**.

## 2. Деплой на Vercel

```bash
# на Mac, в корне репо
npm i -g vercel   # если ещё нет
cd ~/Desktop/bot_calling
git push origin main
vercel login
vercel          # preview
vercel --prod   # production
```

Или: [vercel.com/new](https://vercel.com/new) → Import GitHub `bot_calling` → Deploy.  
Root Directory: репозиторий целиком (используется `vercel.json`).

После деплоя откроется `https://….vercel.app`.

## 3. Домен

1. Vercel → Project → **Settings → Domains** → Add.
2. У регистратора DNS:
   - поддомен: `CNAME bot` → `cname.vercel-dns.com`
   - или как покажет панель Vercel (иногда A-записи).
3. SSL выдаёт Vercel автоматически.

## 4. Смена IP бэкенда

Правьте destination в [`vercel.json`](vercel.json):
```json
"destination": "http://НОВЫЙ_IP:8080/api/:path*"
```
Закоммитьте и задеплойте снова.

## 5. CORS

На бэкенде включён CORS для `*.vercel.app`. Свой домен можно добавить в `.env` на сервере:
```
CORS_ORIGINS=https://bot.example.com,https://your-app.vercel.app
```
(плюс уже есть regex на `*.vercel.app`.)
