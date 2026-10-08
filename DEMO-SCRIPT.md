# OMS360 demo walkthrough (about 15 minutes)

**Before the meeting**
- Stop the server, delete `backend/data/oms360.sqlite` for clean data, then run `npm start` and open **http://127.0.0.1:8000** in Chrome or Edge.
- Open **http://127.0.0.1:8000/outage-map** in a second tab. This is the public page customers see.
- You need internet for the map tiles, live weather and the NHC feed.
- Logins: **steve@powerconnect.ai / admin** or **admin@gmail.com / admin@123** (administrators). Role accounts are under *Other demo roles* on the sign-in page.

**Story.** Bayview Power & Water serves 692,000 electric and 193,000 water customers around Tampa Bay. Two things are happening at once:
- **Hurricane Kyle** is forecast to make landfall in 72 hours as a Category 3. The parent company's storm model has issued a forecast for it.
- The **Tampa Bay Rain Event** is mid-restoration: flooding and fallen trees, with circuit-level ETRs being published.

Three past storms (Hurricanes Delphine and Barrett, and the June Rain Event) are in the system with full records.

---

## 1. Sign in as the operations lead (30 s)
- Click *Other demo roles* → **Dana Whitaker (Operations Manager)**, then **Sign in**.
- *"Every person has a role. A dispatcher, the comms lead and the CEO each see what they're allowed to do, and everything is audited."*

## 2. Overview, preparing for the hurricane (2 min)
- **Header:** Hurricane Kyle, Preparing, landfall in 72 h. The live weather chip is real Tampa weather.
- **KPIs:** about 224k predicted customers out, **640 of about 1,210 line workers needed**, 8 critical facilities at risk, about 150 water lift stations at risk.
- **Map:** predicted outage probability by zone, the forecast track, hospitals, water plants and staging yards.
- **"What we need to do":** recommendations generated from the latest prediction.
  - Open *Why this recommendation?*
  - **Approve "Request 666 mutual-aid line workers"**. Three partner requests are created. Show them later on the Crews page.
  - **Approve "Open all inland staging yards"**. Half the in-house crews move to the yards.
- Ask **Jarvis** (bottom of the page): *"Do I need more people?"*. The answer reflects what you just approved.

## 3. Impact prediction by region and circuit (3 min)
- Go to **Storm Events → Hurricane Kyle → Impact prediction**.
- **Forecast input:** the parent company's storm model forecast, zone by zone (peak gust, rain, surge, arrival).
  - *"Their model tracks the storm. We turn it into what it means for each circuit."*
  - Show **Pull latest from parent model**, **Upload CSV** and **Paste rows**: any forecast source can be loaded, and the prediction re-runs.
- **Predicted restoration by region:** typical customer back and last circuit back, each with a likely range. Central is about 65 h (36–105 h) after landfall. Click a region to filter.
- **Predicted impact by circuit:** the map colours each circuit by predicted share out. Click a line for its restoration range.
- **Circuit table:** predicted customers out, restoration hours with a range bar, confidence, overhead share and years since tree trimming.
- **Run & save prediction** now that mutual aid is requested: the crew shortfall shrinks, so ranges tighten and confidence rises.
- Pick **Cat 4 → Try scenario**. Numbers jump to about 328k customers out and about 1,770 line workers needed. Then switch back to **Parent forecast**.

## 4. Communications approval (1 min)
- Go to **Communications → Pending approval**. The AI drafts are listed with channel, audience and recipient counts.
- Approve one. Send one back with a reason, to show the reject-and-resubmit loop.
- Click **New message** and open the **Audience** list: zones, **regions**, and (for an event in restoration) **individual circuits**.

## 5. The rain event: circuit-level ETRs (3 min)
- Switch the event picker (top bar) to **Tampa Bay Rain Event**.
  - *"Rain events are modelled on rainfall, rate and soil saturation, not wind. Messages talk about flooding, not hurricane categories."*
- Go to **Restoration & ETR**.
  - **By region:** customers out, circuits out, last circuit expected, confidence, circuits published and ready to publish per region.
  - **By circuit:**
    - The map shows circuits with outages coloured by confidence; thicker lines are published.
    - The table lists every circuit with its substation, ETR and confidence.
    - *"Confidence rises as damage is assessed and crews are committed. We only publish what we can stand behind."*
  - Click **Publish all ≥ 80%**. Customers on those circuits get a text with their circuit's own time. Show the texts in **Communications** (audience *Circuit …*).
  - *"If a published ETR moves by more than an hour, those customers get an update automatically."*
- **Public outage map:** blue lines are circuits with their own restoration time. Look up **1208 Bayshore Blvd, Tampa**: once its circuit is published, the answer is for *that circuit*, with a confidence badge. Otherwise it falls back to the zone.

## 6. Landfall: activate the hurricane (1.5 min)
- Switch back to **Hurricane Kyle**. On the Overview, click **Activate event → confirm**.
- Within seconds, **outage tickets stream in live** from the OMS/AMI connector. KPIs switch to customers out, open tickets and crews.
- Go to **Outages** and click **Auto-dispatch**: the nearest idle crews are assigned, critical facilities first.
- Open a ticket. The drawer shows:
  - the ETR with its confidence and circuit;
  - reassign, *Crew on site* and *Mark restored*;
  - the assessment fields and an ETR override;
  - the full history.

## 7. Jarvis (1 min)
- Open **Jarvis** and ask:
  - *"Give me a situation briefing"*
  - *"What are the ETRs in the South Shore region?"*
  - *"When will circuit FDR-TPA-03 be restored?"* (any circuit ID from the Restoration page)
  - *"What if it brings 10 inches of rain?"* (with the rain event selected)

## 8. Reports and calibration (1.5 min)
- Open **Reports**.
- **Circuit ETR confidence, promised vs actual:** *"When we said 80–89%, how often were we right within ±2 hours?"*
  - Bars per confidence band, with a calibrated/overconfident badge.
  - The top bands come out slightly overconfident (about 74% actual for 80–89% promised). *"This is how you set the publishing bar, from evidence."*
  - The note under the chart says the past storms' history is simulated in the sandbox.
- Select **Hurricane Delphine** and show:
  - **ETR accuracy (about 92% within 2 h)**;
  - prediction vs actual (within about 7%);
  - **ETR accuracy by region and by circuit**;
  - customers out over time, causes, zones, crews and communications.

## 9. Network data and audit (1 min)
- Open **Administration → Network**.
  - Every circuit and substation on a map. Routes are sandbox drawings until the utility's GIS feeder layer is imported.
  - **Import feeder GeoJSON** replaces them, matched on feeder ID. **Download template** shows the format.
- **Administration → Audit log**: every approval, forecast import, dispatch, publish and message is recorded.

---

## Handy facts for Q&A
- **Real vs sandbox:**
  - Live: weather, the NHC feed and the map tiles.
  - Seeded: the utility, network (regions, substations, circuits), roster and past storms.
  - Emulated:
    - the OMS/AMI/field-app feed;
    - the parent company's forecast feed;
    - circuit routes;
    - the simulated ETR history behind calibration.
  - Production plugs in the utility's OMS, GIS and the parent model's output.
- **Pre-storm circuit prediction:**
  - Zone hazard comes from the parent model's forecast, or one category / rainfall total.
  - It is shared across the zone's circuits by customers, overhead exposure and vegetation cycle.
  - Ranges widen without an outside forecast, when crews are short, and on heavily damaged or mostly-overhead circuits.
- **Live ETR:**
  - Remaining job hours by damage type (surge ×2.3, flooding ×1.8), divided by crews working the area plus a share of idle crews. Assigned tickets keep their committed ETR.
  - Circuit confidence comes from how settled each ticket is (crew working, assigned, assessed), queue depth, and the zone's past ETR misses.
- **Governance:** role-based permissions; public messages and ETRs need approval; circuit texts use a pre-approved template; full audit trail.
- **What we need from the utility:** GIS feeder layer, customer-to-circuit mapping, outage history for 3–5 storms, the parent model's output format, and live OMS/crew feeds.
