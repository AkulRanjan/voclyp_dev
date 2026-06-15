# VoClyp Console (web)

The VoClyp web console — email/password login, then two role-isolated
interfaces over the same insight data:

- **Manager** (`/manager/*`) — analytics & coaching. The **Pitches** section
  (`/manager/pitches`) is built out: a filterable, sortable table of pitch
  records and a right-side detail drawer (score band, summary, audio, scores,
  signals, coaching).
- **Salesperson** (`/field`) — capture a field visit: consent, in-browser
  recording (16 kHz WAV), submit to the gateway, and view the resulting pitch
  insight in the same drawer the manager sees.

Entry is role-first: a **welcome** screen asks *Manager* or *Sales hero*, then a
second screen takes **email + password** (or create-account, with the role
carried over). You land in the chosen interface and cannot navigate into the
other. There is no in-app switch between roles — the role lives in a
server-signed session token and is re-validated against `/auth/me`, so it can't
be changed by editing browser storage.

## Auth model

- `POST /auth/signup` / `POST /auth/login` → a signed session token (HMAC, with
  an `exp`); `GET /auth/me` returns the authoritative user/role for a token.
- Passwords are stored only as salted PBKDF2 hashes (reusing `voclyp/security`).
- Frontend: `auth/AuthContext` validates the token via `/auth/me` on load;
  `RequireAuth` + `RequireRole` guards gate `/manager/*` (manager) and
  `/field/*` (sales). Token in `localStorage`; role is never trusted from there.
- The `/v1` data plane keeps its own tenant **API key** (set in Settings) — auth
  gates the console; the API key authorizes data calls.

## Run

```powershell
cd web
npm install        # first time only
npm run dev        # http://localhost:5173  (proxies /v1 to the gateway)
```

For real data, run the VoClyp gateway too (`python scripts/demo_app.py` from
the repo root), then in the console go to **Settings**, paste the gateway API
key, and switch the **data source** to *Live VoClyp*. The default source is
**Seed data** (the sample pitches from the spec) so the UI is fully visible
with no backend.

```powershell
npm run build      # typecheck + production build to dist/
npm run preview    # serve dist/ (no /v1 proxy — seed data only)
```

## Layout

```
src/
  components/   Icon, Button, Badge, Chip, Dropdown, Drawer, AudioPlayer (+ css)
  lib/          format (m:ss, dates), bands (score→Poor/Avg/Good), chips (group→tone)
  shell/        Sidebar, AppLayout (Manager/Field), nav, Placeholder
  data/         types, seed, api (/v1 client), voclypAdapter (insight→pitch), source, usePitches
  manager/      ManagerHome, SettingsPage, pitches/ (Page, Table, FilterBar, Drawer)
  field/        FieldRecorderPage, useRecorder (WAV capture)
```

## Data model

`PitchRow` (one brand × script × store × worker record) holds one or more
`PitchInstance` recordings shown in the drawer. See `src/data/types.ts`.

**Live wiring:** `voclypAdapter.ts` maps a VoClyp insight document to the pitch
model. Two gaps are handled explicitly rather than faked:

1. **Coaching scores** (clarity/closing/…) — VoClyp's pipeline does not emit
   pitch-coaching scores yet, so the adapter derives a *provisional* score from
   the signal mix. Swap `provisionalScore`/`subScores` for real values once an
   LLM-backed scoring stage lands.
2. **Recording** — VoClyp destroys the audio after redaction by design, so
   there is no recording to play; the drawer shows that as a privacy guarantee.
