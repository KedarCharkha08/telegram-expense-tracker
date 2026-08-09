# Telegram Expense Tracker

Log expenses by texting a Telegram bot; read them on a Streamlit dashboard.
Zero running cost: Supabase free tier + Render free web service + Streamlit
Community Cloud.

```
Telegram  ──webhook──▶  FastAPI (Render)  ──▶  Supabase (Postgres)
                                                     │
                                          Streamlit dashboard (read-only)
```

## Files

| File | Role |
|---|---|
| `parser.py` | free-text → `ParsedExpense` (amount, category, description, date) |
| `db.py` | Supabase writes/reads, **service key — backend only** |
| `handlers.py` | update → parse → save → reply; also `/today` `/month` `/last` `/undo` |
| `main.py` | FastAPI webhook (`POST /api/telegram-webhook`) |
| `poll_local.py` | run the bot locally with long polling, no deploy needed |
| `set_webhook.py` | register / inspect / delete the webhook |
| `dashboard.py` | Streamlit UI, **publishable key — read-only** |
| `schema.sql` | table, indexes, view, RLS policy |

## Message format

Order doesn't matter; the amount can be anywhere.

```
250 food dinner        dinner 250        ₹1,250 uber to airport
1.2k rent              300 lunch yesterday        450.50 medicines
```

No keyword → `Uncategorized`. `yesterday` / `yday` / `dby` backdate it.

## Local run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # fill in the values
.venv/bin/python -m pytest tests -q
.venv/bin/python poll_local.py
```

`poll_local.py` deletes any registered webhook (Telegram allows one or the
other). Re-register with `set_webhook.py` when you go back to hosted mode.

## Deploy the backend (Render free tier)

1. Push this repo to GitHub — `.env` is gitignored, keep it that way.
2. Render → **New + → Blueprint** → select the repo. `render.yaml` defines the
   service; Render will prompt for the secret env vars.
   (Manual alternative: New + → Web Service, build `pip install -r requirements.txt`,
   start `uvicorn main:app --host 0.0.0.0 --port $PORT`.)
3. Copy the service URL, then point Telegram at it:

   ```bash
   .venv/bin/python set_webhook.py https://your-app.onrender.com
   .venv/bin/python set_webhook.py --info     # confirm, check last_error_message
   ```

### The free-tier cold start

Render free instances sleep after ~15 minutes idle and take ~30–50s to wake.
The webhook answers Telegram immediately and does the work in a background
task, so nothing is lost — but that first expense of the day confirms slowly.
Options: accept it, ping `/healthz` every 10 min from a free cron
(cron-job.org), or move to a platform that doesn't sleep.

Telegram retries deliveries it thinks failed. `expenses.update_id` is UNIQUE,
so a retry is a no-op rather than a duplicate row.

## Deploy the dashboard (Streamlit Community Cloud)

1. share.streamlit.io → **New app** → this repo → main file `dashboard.py`.
2. **Settings → Secrets** → paste the contents of
   `.streamlit/secrets.toml.example` with real values.
3. The app URL is public — that's why `DASHBOARD_PASSWORD` is mandatory and the
   app refuses to render without it.

Streamlit Cloud installs from the root `requirements.txt`. It pulls a few
backend-only packages it doesn't need; harmless, just a slower cold build.

## Security posture

- Webhook verifies `X-Telegram-Bot-Api-Secret-Token`; wrong or missing → 403.
- `ALLOWED_USER_IDS` gates who can write. Empty = locked (the bot replies with
  your Telegram ID so you can fill it in).
- RLS on; the publishable key can only `SELECT` live rows. Writes require the
  secret key, which lives only in Render's env.
- `/undo` soft-deletes (`deleted_at`), so nothing is ever really lost.
- User text is HTML-escaped before being sent back to Telegram.

## Tests

```bash
.venv/bin/python -m pytest tests -q
```

38 tests: parser cases, webhook auth, and handler flow with Supabase and
Telegram stubbed out.
