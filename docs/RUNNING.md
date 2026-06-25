# Running VoClyp locally

VoClyp has two processes:

1. **The backend** — the gateway (API + auth) and the worker (runs the
   pipeline), started together by one script.
2. **The web console** — the React app (login, manager dashboard, salesperson
   recorder).

You need **both** running: the console signs in and reads data through the
gateway.

---

## Prerequisites

- **Python 3.10+** (the backend is stdlib-only except small gateway extras).
- **Node 18+** (only for the web console).
- First time only, install the gateway extras:
  ```powershell
  pip install fastapi uvicorn python-multipart cryptography
  ```

---

## 1. Start the backend (gateway + worker)

From the repo root:

```powershell
python scripts/demo_app.py
```

This starts the gateway + worker, serves the bundled demo UI at
`http://localhost:8000/app/`, and prints a tenant API key (saved in
`data/demo-app/`). Leave it running.

- Free **stub** pipeline by default (no AI credits used).
- For the real Sarvam ASR pipeline instead:
  ```powershell
  $env:SARVAM_API_KEY = "<your key>"
  python scripts/demo_app.py --mode sarvam
  ```

## 2. Start the web console (React)

In a second terminal:

```powershell
cd web
npm install        # first time only
npm run dev
```

Open **http://localhost:5173**. The dev server proxies `/auth` and `/v1` to the
gateway on port 8000, so everything stays same-origin.

---

## Logging in

Open `http://localhost:5173`, pick **Manager** or **Sales hero**, then sign in.
Two demo accounts already exist (password **`voclyp1234`**):

| Role | Email |
|---|---|
| Manager | `manager@voclyp.demo` |
| Sales hero | `sales@voclyp.demo` |

- **Manager** lands on the Pitches dashboard. It shows the sample (**seed**)
  pitches by default; switch to **Live VoClyp** in Settings to read real
  insights from the gateway (no API key needed — your session authorizes it).
- **Sales hero** lands on the recorder: tick consent, record a visit, and submit
  it. It flows through the pipeline and comes back as a pitch insight.
- Managers can invite teammates from **Settings → Invite a teammate** (a
  single-use link). Self-signup as a manager into an existing org is blocked.

> Microphone capture needs a secure context — `localhost` works; over a LAN use
> HTTPS. In `--mode stub` the ASR is a stub, so recorded audio won't transcribe
> meaningfully; use `--mode sarvam` for real speech.

---

## Other things you can run

```powershell
# full end-to-end demo (one conversation, no servers needed)
python scripts/demo.py

# the test suite
python -m unittest discover tests

# the MLOps eval / regression gate
python -m voclyp.mlops.eval --industry fmcg

# build the console for production
cd web; npm run build      # output in web/dist (served by S3/CloudFront or the gateway)
```

---

## Stopping

Press `Ctrl+C` in each terminal. (If a port is stuck, find the process with
`Get-NetTCPConnection -LocalPort 8000` / `5173` and stop it.)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Console login fails / "session expired" | The backend isn't running — start `python scripts/demo_app.py`. |
| Pitches list empty in Live mode | No real conversations yet — record one as a sales hero, or use Seed data. |
| Recorder says "processing…" forever | The worker isn't running; `demo_app.py` runs it — make sure that process is up. |
| Mic button disabled / no audio | Use `http://localhost` (not a LAN IP) and tick consent first. |
| Port already in use | Another instance is running; stop it (see *Stopping*) or change the port. |
| Refused to start (production) | In `VOCLYP_ENV=production` you must set `VOCLYP_SESSION_SECRET`. For local dev, don't set `VOCLYP_ENV`. |

For deploying this to AWS, see **[DEPLOY-AWS.md](DEPLOY-AWS.md)**.
