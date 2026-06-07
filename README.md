# 🛰️ Punjab Opponent Ad Tracker

**AAP Punjab Digital War Room** — ek single-screen dashboard jo Meta Ad Library
se Punjab ke political opponents (BJP / Congress / SAD) ke **active ads**
real-time monitor karta hai. Competitive intelligence ke liye banaya gaya hai:
kaun kitna kharch kar raha hai, kaunse narratives push ho rahe hain, kis region
mein — sab ek jagah.

> **Note:** Agar Meta token na ho ya API fail ho, dashboard automatically
> **DEMO MODE** mein chalega (sample data ke saath) — taaki demo/presentation
> kabhi na ruke.

---

## ✨ Features

- 🎯 Dark "war room" dashboard — stat strip, party chips, region filter, search
- 🃏 Ad cards grid — har card pe spend range, impressions, theme, "View on Meta"
- 📊 Sidebar — party-wise spend bars, top narrative themes, intel alerts
- 🟢 LIVE MONITORING indicator + live clock
- ⏱️ Auto-refresh har 6 ghante (APScheduler + in-memory cache)
- 🔐 Simple session-based login (single admin user, env se)
- 🧪 Graceful demo fallback — token missing/invalid pe crash nahi

---

## 🧱 Tech Stack

| Layer    | Tech                                  |
|----------|---------------------------------------|
| Backend  | Python + Flask + requests             |
| Scheduler| APScheduler (6hr refresh + cache)     |
| Frontend | Single HTML file, vanilla JS + CSS    |
| Deploy   | Railway (GitHub se connect)           |

---

## 📁 Project Structure

```
.
├── app.py                # Flask app: routes, auth, scheduler, cache
├── config.py             # Page IDs, search terms, theme keywords, env config
├── meta_api.py           # Meta API fetch + normalize + demo fallback
├── templates/
│   ├── index.html        # War-room dashboard (vanilla JS+CSS)
│   └── login.html        # Login page
├── static/
│   └── favicon.svg
├── requirements.txt
├── Procfile              # web: gunicorn app:app
├── runtime.txt           # python version
├── .env.example
├── .gitignore
└── README.md
```

---

## 🚀 Local Setup (apne laptop pe test)

```bash
# 1) Virtual env banao
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 2) Dependencies install karo
pip install -r requirements.txt

# 3) Env file banao
copy .env.example .env       # Windows
# cp .env.example .env       # Mac/Linux
# .env kholo, ADMIN_PASS / SECRET_KEY / META_ACCESS_TOKEN bharo

# 4) Run
python app.py
```

Browser mein khol: **http://localhost:5000** → login karo (`ADMIN_USER` /
`ADMIN_PASS`).

> Token na bhara ho? Koi baat nahi — **DEMO MODE** mein chalega.

---

## 🔑 Meta Access Token kaise lein (Graph API Explorer)

1. https://developers.facebook.com/ pe jao → ek **App** banao (type: *Business*).
2. https://developers.facebook.com/tools/explorer/ (Graph API Explorer) kholo.
3. Upar apni app select karo → **Generate Access Token** dabao.
4. Permission/feature: **Ads Library API** ke liye public access hai, par
   political ads ke liye tumhe ek baar **ID verification** (passport/ID upload)
   aur country confirm karni padti hai — Meta ka one-time step hai.
5. Generated token ko copy karke `.env` (ya Railway Variables) mein
   `META_ACCESS_TOKEN=...` set karo.

> ⚠️ Explorer ka token short-lived (kuch ghante) hota hai. Long-running deploy
> ke liye **long-lived token** banao:
> `https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN`
> Iska response wala token use karo (≈60 din valid).

---

## 🆔 Opponent Page ID kaise nikaalein

Har party ki official Facebook Page ka numeric ID chahiye:

1. Us party ki Facebook Page kholo (e.g. "Punjab BJP").
2. **About → Page transparency** section mein scroll karo — wahan **Page ID**
   likha hota hai.
   - Ya: Graph API Explorer mein `?fields=id,name` ke saath page ka username query karo.
   - Ya: koi "find facebook page id" online tool use karo (page URL daal ke).
3. Yeh IDs `config.py` ke `OPPONENT_PAGES` mein, ya env var
   `OPPONENT_PAGES_JSON` mein daalo:

```json
OPPONENT_PAGES_JSON={"BJP":["111","222"],"INC":["333"],"SAD":["444"],"AAP":[]}
```

> Page IDs na ho? `config.py` ka `SEARCH_TERMS` fallback automatically keyword
> search kar lega (e.g. "Punjab BJP", "Shiromani Akali Dal").

---

## 🚂 Railway pe Deploy (GitHub connect)

1. **GitHub** pe repo banao aur ye code push karo:
   ```bash
   git init
   git add .
   git commit -m "Punjab Opponent Ad Tracker"
   git branch -M main
   git remote add origin https://github.com/<tum>/<repo>.git
   git push -u origin main
   ```
   > `.env` commit **mat** karna — `.gitignore` already isse rok raha hai.

2. https://railway.app pe jao → **New Project** → **Deploy from GitHub repo** →
   apna repo choose karo. Railway `requirements.txt` + `Procfile` dekh ke
   khud build kar lega.

3. **Variables** tab kholo aur ye env vars set karo:

   | Key                 | Value                                  |
   |---------------------|----------------------------------------|
   | `META_ACCESS_TOKEN` | tumhara Meta token (khaali = demo mode)|
   | `ADMIN_USER`        | admin                                  |
   | `ADMIN_PASS`        | koi strong password                    |
   | `SECRET_KEY`        | lamba random string                    |
   | `OPPONENT_PAGES_JSON` | (optional) Page IDs ka JSON          |

   > `PORT` Railway khud set karta hai — tumhe add karne ki zaroorat nahi.

4. Deploy hone ke baad Railway ek public URL dega
   (e.g. `https://your-app.up.railway.app`). Kholo → login → dashboard ready ✅

5. (Optional) **Settings → Networking → Generate Domain** se custom domain.

---

## 🔌 API Endpoints

| Method | Route          | Description                              |
|--------|----------------|------------------------------------------|
| GET    | `/`            | Dashboard (login required)               |
| GET    | `/api/ads`     | Cached JSON `{count, ads, mode, ...}`    |
| POST   | `/api/refresh` | Manual refresh trigger (login required)  |
| GET/POST | `/login`     | Login page / submit                      |
| GET    | `/logout`      | Logout                                   |
| GET    | `/health`      | Uptime check (no auth)                   |

---

## 🧩 Theme Auto-detection

Ad text mein keywords ke basis pe theme assign hota hai (`config.py` →
`THEME_KEYWORDS`):

- Drugs / Law & Order · Unemployment / Jobs · Kisan / Agrarian
- Central Schemes · Panthic / Identity · Youth / Education · Development

Naye keywords add karne ho to bas `config.py` edit karo.

---

## ⚠️ Notes & Disclaimers

- Yeh tool **public** Meta Ad Library data hi dikhata hai — koi private data nahi.
- Spend/impressions Meta ke **official range format** mein hi dikhaye jaate hain
  (exact numbers Meta deta hi nahi).
- Single `gunicorn` worker use ho raha hai (Procfile) taaki in-memory cache +
  scheduler ek hi process mein rahe. High traffic ke liye baad mein Redis cache
  laga sakte ho.
- Educational / authorized political-research use ke liye.
