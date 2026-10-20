# OMS360 demo walkthrough: Oklahoma / tornado (about 15 minutes)

**Before the meeting**
- Stop the server and delete `backend/data/oms360-oklahoma.sqlite` for clean data. `OMS360_TERRITORY` defaults to `oklahoma`.
- Run `npm start` and open **http://127.0.0.1:8000** in Chrome or Edge. The first start takes about 20 seconds while it builds the transformer register.
- Open **http://127.0.0.1:8000/outage-map** in a second tab. This is the page customers see.
- Logins:
  - Administrators: **steve@powerconnect.ai / admin** or **admin@gmail.com / admin@123**.
  - Role accounts (see the README) use the password `oms360`. Logins are no longer shown on the sign-in page.

**Story**
- Prairie Sky Power is a fictional electric utility serving about 920,000 customers across Oklahoma. It has five operating regions: Northeast (Tulsa), Central (OKC metro), Southwest, Northwest and Southeast.
- The Storm Prediction Center has a **High Risk** out for this afternoon.
- The planning case, **Central Oklahoma Tornado Outbreak**, has two tornadoes:
  - a long-track **EF4** through Chickasha, Newcastle, Moore and Midwest City;
  - an **EF2** near Jenks and Broken Arrow four hours later.
- The **Tulsa Flash Flood Event** is mid-restoration, with circuit-level ETRs being published.
- Three past events are on file with full records:
  - the May Hail & Wind Event;
  - the Norman–Moore Tornado;
  - the Green Country Flash Flood.

Exact numbers vary a little from one install to the next; the ones below are approximate.

---

## 1. Sign in as the operations lead (30 s)
- *Other demo roles* → **Dana Whitaker (Operations Manager)**.
- Note the branding, the Central time zone and the live Oklahoma City weather chip.

## 2. Storm tab: the tornado paths (2 min)
- Go to **Storm Events → Central Oklahoma Tornado Outbreak**.
- The map shows both damage paths **to scale**, coloured by EF rating. Solid sections have passed; dashed sections are forecast.
- *"A hurricane hits a whole zone. A tornado path is a kilometre wide. Two circuits out of the same substation can see total destruction and nothing at all. So OMS360 predicts tornadoes circuit by circuit."*

## 3. Impact prediction: region → circuit granularity (4 min)
- Open the **Impact prediction** tab.
- **KPIs**:
  - about 83k customers out of 920k;
  - about **17 circuits in the damage paths**, flagged as *rebuild*;
  - about 600 line workers needed;
  - 95% restored in about 5 days.
- **Damage paths table**: each tornado's length × width, the circuits it hits, and the customers and transformers on those circuits.
- **Predicted restoration by region**: Central and Northeast carry almost all the work. *In damage path* shows circuits and transformers per region.
- Click **Central** to filter the circuit map and table. The circuit map draws the tornado corridors over the circuits.
- **Circuit table**:
  - in-path circuits (*EF4 path · rebuild*) have ETAs of roughly 100–150 h with wide ranges;
  - neighbouring circuits in the same town are back within a day.
- The **Transformers** column shows each circuit's health index and Poor/Critical share.
- **Scenario**: switch to **EF5**, then **EF2**, then *Try scenario*. Outages, crews and materials re-scale.

## 3b. Network explorer: state → region → substation → circuit → unit (3 min)
- Open **Intelligence → Network Explorer**. The map shows the Oklahoma outline, the five regions (approximate service areas), substations and the
  tornado paths; the side panel shows the network-impact summary.
- Click **Central** (map or table): the map zooms to the region and the panel lists its substations and highest-risk circuits.
- Click **Moore South** (or any substation), then a circuit marked **in path**: its transformers, poles, reclosers and feeder breaker appear on the
  map coloured by condition. Switch *Colour* to **storm impact** to see which circuits the tornado crosses.
- Click a unit: its record opens in a drawer — age (with install year and reference date), health index and why, missing information,
  predicted exposure (labelled *prediction*), confirmed damage (only from field assessments), history and recommended actions.
- Use the breadcrumbs or **Up a level** to go back; changing region clears the old circuit.

## 4. Asset health: age and condition of major equipment (4 min)
- Open **Intelligence → Asset Health**.
- **KPIs**:
  - about 90k distribution transformers, mean age 22 y;
  - about 17% Poor or Critical;
  - expected failures over the next 12 months;
  - about 87 substation power transformers;
  - the replacement backlog in dollars.
- **By region**: compare mean age, health and backlog. Click **Northeast** to filter.
- **Circuits tab**:
  - the map is coloured by transformer health;
  - sort by *worst health* or *customer risk*;
  - click a circuit to open the drawer.
- **Circuit drawer**:
  - age and health-index histograms;
  - the substation's power transformers (DGA, moisture, through-faults, LTC);
  - every distribution transformer, with the drivers behind its health index.
- If the circuit is in the storm, the drawer says so: *"On the EF4 damage path: plan a rebuild."*
- **Substation transformers tab**: units ranked by risk. Dissolved-gas conditions follow IEEE C57.104.
- *"This is a sandbox register. Load your real asset register with **Import asset register** (CSV, matched by ID) and everything re-scores. That includes the storm prediction."*

- **Replacement plan tab**:
  - drag the budget slider from $5M to $50M and watch customer risk removed climb with diminishing returns;
  - the outlook shows expected failures now, in 5 and in 10 years, with no action and with the plan;
  - *Where the money goes* splits the spend by region, and the list says why each unit is on it;
  - click a region in the table above to plan for that region only.

## 5. Why asset health matters in a storm (1 min)
- Back on the prediction: circuits with older transformers in poor health lose more customers and take longer to restore. More units are replaced rather than re-fused.
- **Materials → Transformers** is counted from each circuit's own register, not from a rule of thumb.
- The overview shows the recommendation *"Pre-stage N distribution transformers, most for the Central region"*.

## 6. Recommendations and Jarvis (2 min)
- **Overview → What we need to do**:
  - *Line up debris-removal contractors and a transmission patrol*;
  - *Pre-stage transformers*;
  - *Request mutual aid* (Texas, Arkansas, Kansas);
  - *Open staging yards outside the tornado watch box*.
- Ask **Jarvis**:
  - *"Which circuits are in the tornado path?"*
  - *"Oldest transformers in the Central region"*
  - *"Transformer health on FDR-MOO-03"*
  - *"What if it's an EF5?"*

## 7. A real tornado warning, then the damage survey (2 min)
- **Storm Events → NWS warnings** lists live tornado and severe-thunderstorm alerts for Oklahoma.
  - When the feed is quiet, click **Load a sample tornado warning (sandbox)**.
- OMS360 projects a planning path along the storm's radar motion. It rates it EF3 from the warning's tags (observed tornado, considerable damage threat) and runs the prediction straight away.
- On the event's **Storm** tab, **Damage paths → Update from damage survey**:
  - paste the surveyed track (or edit the rows);
  - keep *surveyed* on and save.
- The prediction re-runs on the real path, and the confidence goes up.

## 8. Restoration with circuit ETRs (2 min)
- Switch the event (top bar) to **Tulsa Flash Flood Event** and open **Restoration & ETR → Circuit**.
- Show region and circuit ETRs with confidence, and the Transformers column. Transformer jobs on circuits with aging transformers carry longer ETRs.
- Publish the circuits at 80% confidence or above. Customers on those circuits get their own circuit's time by SMS and on the public map.
- In the public tab, look up **1200 S Boston Ave, Tulsa**.

---

**Switching back to the Florida demo**: set `OMS360_TERRITORY=tampa`. It uses its own database file and `DEMO-SCRIPT.md`.
