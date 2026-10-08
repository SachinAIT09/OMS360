# OMS360: Storm Outage Management

OMS360 is an outage management application for utilities facing major storms. It takes a storm from the first National Hurricane Center (NHC) advisory to the after-action report:

- **Storm events** with a real lifecycle: Monitoring → Preparing → Active → Restoring → Closed. Events can be imported live from the NHC or created by hand.
- **Impact prediction**: predicted outages by zone and feeder (including the 80/20 view), critical facilities, the water system, crews needed and materials.
- **AI recommendations**: the "what we need to do" list. Approving one creates real records: mutual-aid requests, staged crews, message drafts, tasks or crew dispatches.
- **Outage tickets** from smart meters (AMI), SCADA, customers and field crews. Each ticket has a status workflow, crew assignment, notes and history.
- **Crews and mutual aid**: the roster, mutual-aid requests from request to release, and staging yards.
- **Restoration and ETR**: estimated restoration times (ETRs) computed from open tickets, assigned crews and damage type. ETRs reach customers only when a supervisor publishes them.
- **Communications**: compose a message or draft it with AI, then submit, approve and send or schedule it. Automated notification rules run alongside.
- **Jarvis**: an assistant you can type or talk to. It answers from live data and can approve recommendations.
- **Reports**: restoration, SAIDI, ETR accuracy, prediction accuracy, crews and communications. Tickets export to CSV.
- **Administration**: users and roles, zones, integrations and a full audit log.
- **Public outage map** at `/outage-map` for customers (no sign-in): address lookup and published ETRs.

Demo utility: **Bayview Power & Water**, Hillsborough County, FL. The utility is fictional; the locations are real.

## Stack
| Layer | Tech |
|---|---|
| Frontend | React 18, TypeScript, Vite, Mantine 7 (UI), TanStack Query, React Router, Leaflet |
| Backend | Python 3.11+ (tested on 3.14), FastAPI, SQLAlchemy 2 |
| Database | SQLite at `backend/data/oms360.sqlite`, created and seeded on first start |
| Live updates | Server-sent events (`/api/stream`) |
| External data | NHC CurrentStorms feed, Open-Meteo or OpenWeather weather, Esri/OpenStreetMap map tiles |

## Run it
From the project root:
```bash
npm install      # frontend packages + Python virtual environment for the backend
npm run dev      # API on :8000 + UI on http://localhost:5173 (hot reload)
npm start        # build the UI, then serve everything at http://127.0.0.1:8000
npm test         # backend tests + TypeScript check
```
API documentation: http://127.0.0.1:8000/docs

### Sign in
Demo logins (shown on the sign-in page): **steve@powerconnect.ai / admin** and **admin@gmail.com / admin@123** (Administrator, full access).
These two accounts are protected: they can't be deactivated, demoted or re-passworded from Administration → Users, and every server start restores them.

The Bayview role accounts below are under *Other demo roles* on the sign-in page; their password is `oms360`.

| Person | Role | Can do |
|---|---|---|
| Marcus Reed | Executive | See everything, approve recommendations and messages, publish ETRs |
| Dana Whitaker | Operations Manager | Everything operational (events, predictions, crews, mutual aid, publishing) |
| Luis Ortega | Dispatcher | Tickets, crew assignment, auto-dispatch |
| Priya Nair | Communications Lead | Write, submit and approve customer messages |
| Sam Patel | Administrator | Everything, plus users, zones, integrations and the audit log |

To start over with fresh data, stop the server and delete `backend/data/oms360.sqlite`.

### Hosting on Render's free plan
- **No persistent disk.** The database is rebuilt from seed data every time the service restarts or wakes up, so changes made in the app (users, zones, events) don't last.
- **Sign-ins survive restarts.** Login tokens are signed with `OMS360_SECRET`; `render.yaml` generates it once.
- **Sleeps after ~15 min idle.** The first request then takes up to a minute. The sign-in page shows a "waking up" note and keeps retrying.
- **Keeping it awake.** Point a free uptime monitor (UptimeRobot, cron-job.org) at `https://<your-app>.onrender.com/api/health` every 10 minutes. One always-on service fits within the 750 free instance-hours a month.

## Integrations
- **NHC**: Storm Events → *Import from NHC* lists the active storms from `nhc.noaa.gov/CurrentStorms.json`.
- **Weather**: Open-Meteo works without a key. To use OpenWeather and get radar map overlays, add a key in Administration → Integrations, or set the `OPENWEATHER_API_KEY` environment variable. The key stays on the server.
- **OMS/AMI connector** (Administration → Integrations):
  - **Sandbox** (default) emulates the utility's OMS/AMI and field mobile app. While an event is Active, smart-meter outages open tickets, field crews accept and complete work, and mutual-aid partners confirm and arrive (time-compressed).
  - **Off** means tickets come only from users or the API.
  - A production deployment replaces `services/connector.py` with the utility's OMS adapter.

## Project layout
```
backend/app/
  models.py        SQLAlchemy models (events, predictions, outages, crews, mutual aid, messages, audit, ...)
  auth.py          sign-in tokens, roles and permissions
  seed.py          first-run data (network, roster, users, two past storms, current event)
  services/        prediction, ops (tickets + ETR), recommendations, comms, jarvis, nhc, connector, events
  routers/         REST API: auth, events, field (outages/crews/mutual aid/restoration), engagement, admin
backend/tests/     pytest: auth & roles, storm lifecycle, dispatch & ETR, publishing, comms approval, Jarvis, reports, NHC
frontend/src/
  layout/          app shell (navigation, event switcher, search, notifications)
  pages/           Overview, Storm events, Event detail, Outages, Restoration, Crews, Communications, Jarvis, Reports, Admin, Login, Public map
  components/      map, ticket drawer, recommendation card, Jarvis chat, badges
  api/, auth/      typed client, query hooks, auth and current-event context
legacy/            original single-file prototype (reference only)
```
