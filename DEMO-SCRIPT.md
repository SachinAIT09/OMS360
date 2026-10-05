# OMS360 demo walkthrough (about 10 minutes)

**Before the meeting**
- Stop the server, delete `backend/data/oms360.sqlite` for clean data, then run `npm start` and open **http://127.0.0.1:8000** in Chrome or Edge.
- Open **http://127.0.0.1:8000/outage-map** in a second tab. This is the public page customers see.
- You need internet for the map tiles, live weather and the NHC feed.

**Story.** Bayview Power & Water serves 692,000 electric and 193,000 water customers around Tampa Bay. Hurricane Kyle is forecast to make landfall in 72 hours as a Category 3. Two past storms (Delphine and Barrett) are already in the system with full records.

---

## 1. Sign in as the operations lead (30 s)
- Click **Dana Whitaker (Operations Manager)** on the sign-in page, then **Sign in**.
- *"Every person has a role. A dispatcher, the comms lead and the CEO each see what they're allowed to do, and everything is audited."*

## 2. Overview, preparing for the storm (2 min)
- **Header:** Hurricane Kyle, Preparing, landfall in 72 h. The live weather chip is real Tampa weather.
- **KPIs:** 208k predicted customers out, **640 of 1,126 line workers**, 9 critical facilities at risk, 150 water lift stations at risk.
- **Map:** predicted outage probability by zone, the forecast track, hospitals, water plants and staging yards.
- **"What we need to do":** recommendations generated from the latest prediction.
  - Open *Why this recommendation?*
  - **Approve "Request 576 mutual-aid line workers"**. Three partner requests are created. Show them later on the Crews page.
  - **Approve "Open all inland staging yards"**. Half the in-house crews move to the yards.
  - **Approve "Draft the pre-storm customer campaign"**. Five AI drafts go to the approval queue.
- Ask **Jarvis** (bottom of the page): *"Do I need more people?"*. The answer reflects what you just approved.

## 3. Storm event and prediction (1.5 min)
- Go to **Storm Events**. Show **Import from NHC** (the live National Hurricane Center feed) and the past storms.
- Open **Hurricane Kyle → Impact prediction**.
- Pick **Cat 4 → Try scenario**. Numbers jump to about 328k customers out and about 1,770 line workers needed. Then switch back to the saved prediction.
- Show the **80/20 feeder chart**, critical facilities, water system and materials.

## 4. Communications approval (1 min)
- Go to **Communications → Pending approval**. The AI drafts are listed with channel, audience and recipient counts.
- Approve one. Send one back with a reason, to show the reject-and-resubmit loop.
- Click **New message → Draft with AI**, then show the channel preview and the SMS segment counter.

## 5. Landfall: activate the event (2 min)
- On the Overview, click **Activate event → confirm**.
- Within seconds, **outage tickets stream in live** from the OMS/AMI connector (toasts: "New outages"). KPIs switch to customers out, open tickets and crews.
- Go to **Outages**. Show the filters, the map view and sorting. Then click **Auto-dispatch**: the nearest idle crews are assigned, critical facilities first.
- Open a ticket. The drawer shows:
  - the committed ETR and job time;
  - reassign, *Crew on site* and *Mark restored*;
  - the assessment fields (cause, damage, priority) and an ETR override;
  - the full history.
- *"Field crews update these from their mobile app. In the sandbox you'll see tickets move to In progress and Restored on their own."*

## 6. Restoration and publishing ETRs (1.5 min)
- Go to **Restoration & ETR**. Each zone has an ETR, a confidence level, the crews working there and a restoration curve.
- Click **Publish all**. *"Customers now see a specific time instead of 'multiple days', and get a text."*
- Switch to the **public outage map** tab and look up **1208 Bayshore Blvd, Tampa**. It shows the estimated restoration time, the number of crews working and a confidence badge.
- Unpublish a zone: the public page goes back to "Outage confirmed". *"Nothing goes public without approval."*

## 7. Jarvis (1 min)
- Open **Jarvis**. Click the mic and ask:
  - *"Give me a situation briefing"*
  - *"When will Riverview be restored?"*
  - *"How many tickets are unassigned?"*
- Click an **Approve** button inside a Jarvis answer. Jarvis can act, within your role's permissions.

## 8. Reports and audit (1 min)
- Open **Reports** and select Hurricane Delphine. Show:
  - customers out over time;
  - SAIDI;
  - **ETR accuracy (about 94% within 2 h)**;
  - prediction vs actual (within about 7%);
  - causes, zones, crews and communications.
- Sign in as **Sam Patel (Administrator)** and open **Administration → Audit log**. Every approval, dispatch, publish and message is recorded.

---

## Handy facts for Q&A
- **Real vs sandbox:**
  - Live: weather, the NHC feed and the map tiles.
  - Seeded: the utility, network and roster.
  - Emulated (sandbox connector): the OMS/AMI/field-app feed. Production plugs in the utility's OMS.
- **ETR method:** remaining job hours by damage type (surge ×2.3) ÷ crews working the zone plus a share of idle crews. Assigned tickets keep their committed ETR. ETRs are recalculated on every change.
- **Governance:** role-based permissions; public messages and ETRs need approval; full audit trail.
