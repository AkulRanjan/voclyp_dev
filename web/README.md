# VoClyp Console (web)

The VoClyp web console — two interfaces over the same insight data:

- **Manager** (`/manager/*`) — analytics & coaching. The **Pitches** section
  (`/manager/pitches`) is built out: a filterable, sortable table of pitch
  records and a right-side detail drawer (score band, summary, audio, scores,
  signals, coaching).
- **Salesperson** (`/field`) — capture a field visit: consent, in-browser
  recording (16 kHz WAV), submit to the gateway, and view the resulting pitch
  insight in the same drawer the manager sees.

Switch between them from the sidebar footer.

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
