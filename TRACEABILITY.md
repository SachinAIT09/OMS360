# OMS360 Oklahoma / tornado / asset intelligence — requirements traceability

Branch `oklahoma-tornado`. Status key: **Verified** = implemented and checked by an automated test or a recorded manual check;
**Implemented** = built, not fully verified; **Blocked** = needs something outside this repo; **N/A** = not applicable, with reason.

All network, customer, equipment and storm data in the demo is **synthetic** (labelled "Simulation data" in the app). No real AEP / PSO
infrastructure, customers or live outages are represented.

## 1. Oklahoma tornado scenario

| Requirement | Where | Verification | Status |
|---|---|---|---|
| Oklahoma geographic focus, tornado scenario | `backend/app/territories/oklahoma.py`, `OMS360_TERRITORY` | `tests_oklahoma/test_oklahoma_tornado.py::test_profile_and_network_are_oklahoma`; e2e 1 | Verified |
| Florida/hurricane demo preserved | `territories/tampa.py` | `tests/` (40 tests, unchanged assertions) | Verified |
| Tornado visuals: paths to scale, EF colours, twister marker, legend | `components/TerritoryMap.tsx`, `NetworkExplorerPage.tsx` | e2e 1, 1b | Verified |
| Tornado direction, timeline | Event → Storm tab timeline slider | e2e 1b | Verified |
| Impact corridor → affected circuits / substations / transformers | `services/prediction.py` (`_predict_tornado`), `asset_history.storm_impact` | `test_tornado_prediction_is_built_from_circuits`, `test_geo_search_and_impact` | Verified |
| Layer toggles + legend | Network explorer chips, `MapKey` | e2e 1b (storm layer off/on) | Verified |
| State boundary | `territories/geo/oklahoma.json` (US Census outline, simplified), `/api/network/geo` | `test_geo_search_and_impact` (lat range 33.6–37.0) | Verified |
| Service-region boundaries | Convex hull of each region's circuits, labelled approximate | `test_geo_search_and_impact` | Verified (approximate by design) |
| Official forecasts not implied | "Simulation data" header badge, "prediction" labels, NWS import labelled planning path | e2e 1 | Verified |
| Live tornado warnings | NWS alerts (`services/nws.py`); sandbox sample when quiet | `test_nws_warning_parsing`, `test_import_warning_and_replace_with_survey` | Verified (live feed reachable; no OK warnings active during testing) |
| Real AEP infrastructure | — | — | Blocked: needs AEP GIS / asset data (imports exist: GeoJSON feeders, CSV assets) |

## 2. Regional and circuit granularity

| Requirement | Where | Verification | Status |
|---|---|---|---|
| Hierarchy state → region → substation → circuit → unit | `/network` explorer, `/api/network/substations[/id]`, `/api/assets/circuits/{id}`, `/asset/:id` | `test_hierarchy_is_consistent`; e2e 2, 3 | Verified |
| Statewide overview (regions, circuits, substations, customers, assets to inspect) | `StormImpactCard`, explorer state panel | `test_geo_search_and_impact`; e2e 1 | Verified |
| Region drill-down; filters affect map, cards, tables | Explorer region panel; Asset Health region filter | e2e 2, 5 | Verified |
| Circuit drill-down: id, substation, region, equipment, storm exposure, outages | Explorer circuit panel | e2e 3; `test_hierarchy_is_consistent` | Verified |
| Equipment belongs to the selected circuit | `circuit_markers`, `circuit_detail` | `test_hierarchy_is_consistent` (marker count = DB count) | Verified |
| Breadcrumbs / up a level / reset; stale selection cleared | `select()` in explorer clears lower levels | e2e 2, 3, 5 | Verified |
| Circuit topology | Routes are sandbox drawings, labelled "sandbox route" | — | Implemented; real topology Blocked on utility GIS |
| Empty / invalid selections | "Region not found", "Circuit not found", error states | e2e 8 | Verified |

## 3. Asset age, health and prioritisation

| Requirement | Where | Verification | Status |
|---|---|---|---|
| Transformers + substations, breakers, reclosers, poles | `models.Asset`, `services/assets.py` | `test_every_equipment_type_and_missing_data_are_represented` | Verified |
| Age from install year with reference date shown | `serial()` (`age`, `age_reference` = today in territory TZ) | `test_age_matches_an_independent_calculation`; e2e 4 | Verified |
| Missing / invalid / future dates | Blank kept as Unknown; future or < 1900 rejected on import | `test_import_asset_register`, e2e 4 | Verified |
| Health model transparent, configurable, labelled illustrative | `services/asset_model.py`; Health model tab; weights via `/api/admin/assets/model` | `test_health_weights_are_adjustable_and_rescore` | Verified |
| Age alone is not proof of poor health | Penalties from inspection, tests, loading | `test_age_alone_does_not_make_a_unit_poor` | Verified |
| Known condition vs calculated vs missing vs confirmed damage | Drivers, gaps, confidence, `status` (damaged only via field assessment), "prediction" labels | `test_confirmed_damage_follows_field_assessment`, `test_exposure_is_a_prediction_not_damage` | Verified |
| Risk & maintenance prioritisation with reasons | Risk score, recommendations, work orders, replacement planner | `test_work_orders`, `test_replacement_plan` | Verified |
| Asset detail (history, exposure, outages, actions) | `components/AssetDetail.tsx`, `/asset/:id` | e2e 3, 4, 7 | Verified |
| Same record from map, table, drawer, search, assistant | `/asset/:id` links everywhere | e2e 3 (drawer), 7 (table) | Verified |
| Backward-compatible schema change | `db._upgrade_assets` (rebuild table keeping rows) | Ran on copies of the two existing databases: no rows lost, integrity ok | Verified (manual) |
| Utility-validated health scores | — | — | Blocked: needs AEP asset-management engineering review |

## 4. UI/UX, themes, responsiveness

| Requirement | Verification | Status |
|---|---|---|
| Light and dark themes across main screens; preference persists | e2e 6 + screenshots reviewed (`frontend/e2e-screens/themes`) | Verified |
| Responsive at 1440, 820, 390 px; no sideways scroll | e2e 9 + screenshots reviewed (`frontend/e2e-screens/responsive`) | Verified |
| Loading / empty / error states | e2e 8 | Verified |
| Keyboard / labels | Drawer close button labelled; sliders keyboard-operable (e2e 1b) | Implemented (no full WCAG audit) |
| Styling system | Mantine kept; Tailwind not added (would be a second styling system) | N/A |

## 5. Quality checks

See the final report for commands and results: backend pytest (Tampa + Oklahoma), pyflakes, pip-audit, ESLint, TypeScript, Vitest,
production build, Playwright e2e (scenarios 1–9), npm audit.
