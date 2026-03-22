# Contributing to Shadowbroker

> **Global Threat Intercept — Real-Time Geospatial Intelligence Platform**  
> Contributor guide covering installation, Spain + USA CCTV integration, alert pipeline, STIX 2.1 export, analyst workflow, and code style.

---

## Table of Contents

1. [What Is Shadowbroker](#1-what-is-shadowbroker)
2. [How to Contribute](#2-how-to-contribute)
3. [Code Style](#3-code-style)
4. [Installation from Scratch](#4-installation-from-scratch)
5. [Running the Platform](#5-running-the-platform)
6. [Spain CCTV Integration](#6-spain-cctv-integration)
7. [USA CCTV Integration](#7-usa-cctv-integration)
8. [CCTV Alert Pipeline](#8-cctv-alert-pipeline)
9. [STIX 2.1 Export](#9-stix-21-export)
10. [Analyst Walkthrough — Step by Step](#10-analyst-walkthrough--step-by-step)
11. [Suggested Next Contributions](#11-suggested-next-contributions)
12. [Legal Status of All Data Sources](#12-legal-status-of-all-data-sources)
13. [Quick Reference](#13-quick-reference)
14. [Extended Documentation](#14-extended-documentation)

---

## 1. What Is Shadowbroker

Shadowbroker is an open-source real-time geospatial intelligence dashboard. It aggregates data from over 15 public APIs and renders everything on a single dark-ops map — aircraft, ships, satellites, earthquakes, conflict zones, CCTV cameras, and GPS jamming zones, all live.

Built with **Next.js**, **MapLibre GL**, **FastAPI**, and **Python**.

### Architecture

| Component | Description |
|-----------|-------------|
| Frontend | Next.js + MapLibre GL. Runs on `localhost:3000`. Renders the WebGL map and all UI panels. Polls the backend every 15–60 seconds. |
| Backend | FastAPI (Python). Runs on `localhost:8000`. Scheduler fetches all data sources and serves them compressed as GeoJSON with ETag caching. |

### Data Layers

| Layer | Source | Default |
|-------|--------|---------|
| Commercial Flights | OpenSky Network | ON |
| Military Flights | adsb.lol military endpoint | ON |
| AIS Vessels (25k+) | aisstream.io WebSocket | ON |
| Satellites | CelesTrak TLE + SGP4 | ON |
| Earthquakes | USGS real-time feed | ON |
| CCTV Mesh | TfL, NYC DOT, Austin TxDOT, Singapore LTA, Spain (DGT + Madrid), USA (7 states) | OFF |
| GPS Jamming | NAC-P degradation analysis | ON |
| Ukraine Frontline | DeepState Map GeoJSON | ON |
| Global Incidents | GDELT Project | ON |

---

## 2. How to Contribute

Since you don't have write access to the upstream repo, the workflow is:

```
Fork → Branch → Build → Test → Pull Request
```

**Step by step:**

1. Go to `https://github.com/BigBodyCobain/Shadowbroker` and click **Fork**
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/Shadowbroker.git`
3. Create a feature branch: `git checkout -b feature/your-feature-name`
4. Make your changes and test locally
5. Commit: `git add .` then `git commit -m "feat: description"`
6. Push: `git push origin feature/your-feature-name`
7. Open a Pull Request from your fork to the original repo

> **PowerShell note:** Use `;` instead of `&&` to chain commands. Example: `git add . ; git commit -m "message"`

---

## 3. Code Style

These rules apply to all contributions to this repository. Follow them consistently — PRs that violate them will be asked to revise before merge.

### Python (Backend)

**Formatting**
- Indentation: 4 spaces. No tabs.
- Max line length: 120 characters.
- Use f-strings for string formatting. Not `.format()` or `%`.
- One blank line between methods inside a class. Two blank lines between top-level definitions.

**Naming**
- Classes: `PascalCase` — e.g. `WSDOTIngestor`, `CCTVAlertPipeline`
- Functions and variables: `snake_case` — e.g. `fetch_data`, `source_agency`
- Constants: `UPPER_SNAKE_CASE` — e.g. `DB_PATH`, `WSDOT_URL`
- Private helpers: prefix with `_` — e.g. `_detect_media_type`, `_proxy`

**Ingestor pattern**
Every new CCTV source must subclass `BaseCCTVIngestor` and implement `fetch_data()`. The returned list of dicts must always include these keys:

```python
{
    "id": str,            # Unique. Format: "PREFIX-{source_id}"
    "source_agency": str, # Human-readable source name
    "lat": float,
    "lon": float,
    "direction_facing": str,  # Location label
    "name": str,              # Same as direction_facing — used by the UI panel
    "media_url": str,         # Always route through _proxy() for external URLs
    "refresh_rate_seconds": int,
}
```

**Never** return a camera dict with `media_url: ""` — cameras with empty URLs are invisible in the UI. If a live API is unavailable, use seed cameras with confirmed image URLs.

**Proxy rule**
All external image URLs must go through the backend proxy helper:

```python
from urllib.parse import quote as urlquote

def _proxy(raw_url: str) -> str:
    if not raw_url:
        return ""
    if raw_url.startswith("/api/cctv/proxy-image"):
        return raw_url
    return f"/api/cctv/proxy-image?url={urlquote(raw_url, safe='')}"
```

If you add a new image host, add it to `_CCTV_PROXY_ALLOWED_HOSTS` and `_CCTV_REFERERS` in `backend/main.py`.

**Error handling**
- Wrap all network calls in try/except. Log failures with `logger.warning()` or `logger.error()`, never `print()`.
- Never let an ingestor crash the scheduler. Return `[]` or fall back to seed cameras on any exception.
- Use the existing `fetch_with_curl()` utility for HTTP — it handles timeout, retry, and curl fallback automatically.

**Imports**
- Standard library first, then third-party, then local — one blank line between each group.
- No wildcard imports (`from module import *`).

### TypeScript (Frontend)

**Formatting**
- Indentation: 4 spaces.
- Semicolons: always.
- Single quotes for strings. Template literals for interpolation.
- No `any` types unless explicitly unavoidable — add a comment explaining why.

**Naming**
- Components: `PascalCase` — e.g. `MaplibreViewer`, `NewsFeed`
- Functions and variables: `camelCase` — e.g. `buildCctvGeoJSON`, `selectedEntity`
- Types and interfaces: `PascalCase` — e.g. `CCTVCamera`, `SelectedEntity`
- Constants: `UPPER_SNAKE_CASE` for module-level values

**GeoJSON builder pattern**
Every new map layer needs a builder function in `geoJSONBuilders.ts`. The function must:
- Accept the data array and an optional `InViewFilter`
- Return `null` if the array is empty or undefined — never an empty FeatureCollection
- Include all fields the click handler and detail panel need in `properties`

```typescript
export function buildMyLayerGeoJSON(items?: MyType[], inView?: InViewFilter): FC {
    if (!items?.length) return null;
    return {
        type: 'FeatureCollection' as const,
        features: items
            .filter(i => i.lat != null && i.lon != null && (!inView || inView(i.lat, i.lon)))
            .map((item, idx) => ({
                type: 'Feature' as const,
                properties: {
                    id: item.id || idx,
                    type: 'my_type',   // must match the click handler switch
                    name: item.name || 'Unknown',
                },
                geometry: { type: 'Point' as const, coordinates: [item.lon, item.lat] }
            }))
    };
}
```

**Layer interactivity**
Any new clickable layer must be added to `activeInteractiveLayerIds` in `MaplibreViewer.tsx`. Both the cluster layer (if using clustering) and the individual dot layer must be listed.

**Type definitions**
Every new data type must have an interface in `frontend/src/types/dashboard.ts`. No implicit `any` for API data shapes.

### Git

- Commit messages follow Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`
- One logical change per commit. Do not combine unrelated fixes.
- Never commit `.env`, `cctv.db`, `__pycache__/`, or `node_modules/`.
- Branch names: `feature/short-description` or `fix/short-description`

---

## 4. Installation from Scratch

### 4.1 Prerequisites

| Tool | Where to get it | Verify |
|------|----------------|--------|
| Python 3.10–3.12 | https://python.org — check **Add to PATH** during install | `python --version` |
| Node.js 18+ LTS | https://nodejs.org — use the LTS button | `node --version` |
| Git | https://git-scm.com | `git --version` |

> After installing each tool, **close PowerShell completely and reopen it**. PATH changes only take effect in new terminal sessions.
> 
> ⚠️ Python 3.13+ has compatibility issues with some dependencies. Use **3.11 or 3.12**.

### 4.2 Clone the Repository

```powershell
cd C:\Users\YourName
git clone https://github.com/AlborzNazari/Shadowbroker.git
cd Shadowbroker
```

### 4.3 Install Backend Dependencies

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
npm install ws
```

### 4.4 Install Frontend Dependencies

```powershell
cd ..\frontend
npm install
```

### 4.5 Create the .env File

```powershell
cd ..\backend
@"
AIS_API_KEY=dummy
OPENSKY_CLIENT_ID=dummy
OPENSKY_CLIENT_SECRET=dummy
"@ | Out-File -Encoding utf8 .env
```

> Dummy values let the server start. Get a free key at [aisstream.io](https://aisstream.io) for live ship tracking.

---

## 5. Running the Platform

Open **two PowerShell windows** with venv activated in each:

**Window 1 — Backend:**
```powershell
cd C:\Users\YourName\Shadowbroker\backend
venv\Scripts\activate
python main.py
```

**Window 2 — Frontend:**
```powershell
cd C:\Users\YourName\Shadowbroker\frontend
npm run dev
```

Cameras ingest automatically on startup via `_run_all_cctv_ingestors()` called from `update_all_data()`. No manual seeding step required.

### Verify Everything Is Running

| What | URL |
|------|-----|
| Live map dashboard | http://localhost:3000 |
| Backend health check | http://localhost:8000/api/health |
| API documentation | http://localhost:8000/docs |
| STIX bundle | http://localhost:8000/api/stix/bundle?pretty=true |
| CCTV camera count | http://localhost:8000/api/health → `sources.cctv` |

### Common Warnings (Non-Fatal)

| Warning | Cause | Action |
|---------|-------|--------|
| `AIS Stream error: Api Key Is Not Valid` | `.env` has `AIS_API_KEY=dummy` | Get a free key at aisstream.io |
| `Cannot find module 'ws'` | Node ws package missing | Run `npm install ws` in backend folder |
| `Too Many Requests` for stock tickers | Yahoo Finance rate limit | Harmless, retries automatically |
| `WSDOTIngestor: using seed cameras` | WSDOT API changed endpoint | Expected — seeds are used as fallback |

---

## 6. Spain CCTV Integration

### 6.1 What Was Added

`backend/services/spain_cctv.py` adds camera ingestors following the `BaseCCTVIngestor` pattern:

| Source | Coverage | Cameras | API Key |
|--------|----------|---------|---------|
| Madrid City Hall (`datos.madrid.es`) | Madrid urban roads and city centre | 357 | None |
| DGT Spain (`infocar.dgt.es`) | National motorways A-2, A-4, A-6, AP-7 | 20+ | None |
| Barcelona, Valencia, Sevilla, Zaragoza, Bizkaia, Málaga | Regional road authorities | varies | None |

### 6.2 What You See on the Map

Enable **CCTV Mesh** from the left panel and zoom into Spain:

- Green dots clustered across Madrid — 357 cameras from the Madrid City Hall KML feed
- Green dots along motorways — DGT national road cameras
- Click any green dot — opens detail panel with camera name, source, and live still image
- Images refresh every 5–10 minutes

### 6.3 Legal Basis

Both sources are published under Spain's open data framework — **Ley 37/2007** implementing the **EU PSI Directive 2019/1024**. Free reuse with attribution. Attribution is provided via the `source_agency` field stored in the DB and displayed in the UI.

---

## 7. USA CCTV Integration

### 7.1 What Was Added

`backend/services/usa_cctv.py` adds 7 state DOT camera ingestors covering US military installation corridors. All image URLs route through the backend proxy at `/api/cctv/proxy-image` to avoid CORS and 403 errors.

| State | Key Installations Covered | Status |
|-------|--------------------------|--------|
| Washington (WSDOT) | JBLM, Bremerton Naval, Whidbey Island NAS, Fairchild AFB | Seed cameras (API endpoint changed) |
| Virginia (VDOT) | Pentagon, Quantico MCB, Langley AFB, Norfolk Naval | Live with `VDOT_API_KEY`, seeds without |
| Texas (TxDOT) | Fort Cavazos, Fort Bliss, Dyess AFB, Lackland AFB | Seed cameras (API DNS unavailable) |
| Nevada/Utah | Nellis AFB, Area 51 corridor, Hill AFB, Dugway Proving Ground | Seed cameras (API changed) |
| Florida (FDOT) | MacDill AFB, Patrick SFB, Eglin AFB, NAS Jacksonville | Live via fl511.com |
| California (Caltrans) | Camp Pendleton, Edwards AFB, Vandenberg SFB, MCAS Miramar | Live via cwwp2.dot.ca.gov |
| Georgia (GDOT) | Fort Moore, Fort Eisenhower, Robins AFB, Moody AFB | Live via 511ga.org |

> **Note on seed cameras:** States marked "seed cameras" fall back to hardcoded coordinates with confirmed image URL patterns when their live API is unreachable. The locations are accurate — the images are real DOT feeds from those corridors. If a seed image shows NO SIGNAL, that specific camera ID has rotated on the DOT side. See Section 11 for how to contribute updated IDs.

### 7.2 Architecture: The Proxy

All external camera images are served through a backend proxy endpoint to prevent CORS failures:

```
Browser → /api/cctv/proxy-image?url=<encoded_url> → FastAPI → DOT image server → response
```

The proxy allowlist in `main.py` controls which domains can be proxied. Adding a new camera source requires adding its image host to both `_CCTV_PROXY_ALLOWED_HOSTS` and `_CCTV_REFERERS`.

### 7.3 Adding a New US State

1. Create a new ingestor class in `usa_cctv.py` subclassing `BaseCCTVIngestor`
2. Implement `fetch_data()` returning dicts with all required fields (see Code Style section)
3. Add the image host to `_CCTV_PROXY_ALLOWED_HOSTS` and `_CCTV_REFERERS` in `main.py`
4. Add an instance to `_run_all_cctv_ingestors()` in `data_fetcher.py`
5. Add the instance to the scheduler in `start_scheduler()` in `data_fetcher.py`

### 7.4 Optional API Keys

```
VDOT_API_KEY=your_key    # Free registration at https://www.511virginia.org/developers
                          # Without this key, Virginia falls back to seed cameras
```

Add to `backend/.env`.

### 7.5 Legal Basis

All sources are US Government public open data under state DOT open data policies. Free reuse with attribution. No sources require paid access or proprietary agreements.

---

## 8. CCTV Alert Pipeline

### 8.1 What It Does

`backend/services/cctv_alert.py` connects the camera layer to active threat events automatically. It runs every 5 minutes and does three things in sequence.

### 8.2 Stage 1 — Spatial Join

For each active GPS jamming zone and military holding pattern, find every camera within 25 km:

```python
def cameras_within_radius(cameras, event_lat, event_lon, radius_km=25):
    return [cam for cam in cameras
            if haversine(event_lat, event_lon, cam['lat'], cam['lon']) <= radius_km
            and cam['media_url']]
```

### 8.3 Stage 2 — Change Detection

Fetch the current still image, convert to 160×120 grayscale, compare against a rolling baseline:

```python
def _pixel_change_score(frame_a, frame_b):
    diff = np.abs(frame_a - frame_b)
    return float(diff.mean() / 255.0)
```

| Score | Meaning |
|-------|---------|
| < 0.02 | Lighting change only — ignore |
| 0.02–0.08 | Normal traffic variation |
| 0.08–0.12 | Moderate change — log only |
| > 0.12 | **Alert fires** |
| > 0.30 | Possible camera blackout |

### 8.4 Stage 3 — STIX observed-data Export

Alerts are written as STIX 2.1 `observed-data` objects and injected into the bundle at `/api/stix/bundle`:

```python
{
  "type": "observed-data",
  "labels": ["cctv-anomaly-near-jamming"],
  "extensions": {
    "extension-definition--shadowbroker-cctv-alert": {
      "camera_id": "WSDOT-S001",
      "change_score": 0.22,
      "correlated_event_id": "JAM-47.150--122.440",
      "distance_km": 8.3
    }
  }
}
```

### 8.5 Alert Types

| Alert Type | Trigger |
|------------|---------|
| `CCTV_ANOMALY_NEAR_JAMMING` | Camera within 25km of active GPS jamming zone, change score > 0.12 |
| `CCTV_ANOMALY_NEAR_HOLDING` | Camera within 25km of military ISR holding pattern, change score > 0.12 |
| `CCTV_BLACKOUT` | Camera fails 3 consecutive fetches near an active event |

---

## 9. STIX 2.1 Export

### 9.1 What It Does

`backend/services/stix_exporter.py` wraps Shadowbroker's live data into a STIX 2.1 bundle consumable by enterprise SIEMs.

### 9.2 Exported Object Types

| STIX Type | Source Data | What It Represents |
|-----------|-------------|-------------------|
| `incident` | GDELT conflict events | Geopolitical incidents with tone score, country, themes |
| `location` | GPS jamming zones | Geographic interference areas with severity % |
| `indicator` | Military holding patterns | ISR orbit activity — callsign, type, coordinates |
| `relationship` | Auto-generated | Links each incident to its geographic location |
| `observed-data` | CCTV alert pipeline | Camera anomalies near active jamming or ISR events |

### 9.3 Endpoint

```
GET http://localhost:8000/api/stix/bundle
GET http://localhost:8000/api/stix/bundle?pretty=true
```

### 9.4 Consuming the Bundle

| Platform | Method |
|----------|--------|
| Splunk Enterprise Security | TAXII feed connector or manual bundle import |
| Microsoft Sentinel | Threat Intelligence Platforms data connector |
| OpenCTI | STIX2 import connector — supports live polling |
| IBM QRadar | STIX/TAXII threat intelligence feed configuration |

---

## 10. Analyst Walkthrough — Step by Step

The value of Shadowbroker is correlation — when multiple independent data sources light up in the same geographic area at the same time.

### Scenario: GPS Jamming Detected Over Spain

**Step 1 — Check GPS Jamming Zones.** Look for red square overlays on the map. Each overlay shows a severity percentage derived from NAC-P degradation across aircraft in that grid cell.

**Step 2 — Cross-Reference Military Flights.** Look for holding patterns near the red overlay. RC-135 Rivet Joints, E-3 Sentry AWACS, and P-8 Poseidons near a jamming zone strongly indicate intentional electronic warfare.

**Step 3 — Enable CCTV Mesh.** Zoom into Spain. Click green camera dots near the jamming zone. Look for unusual ground activity: light traffic at peak hours, police presence, empty access roads near installations.

**Step 4 — Check GDELT Global Incidents.** Look for GDELT event markers in the same region from the past 6 hours with MILITARY or SECURITY themes and tone scores below -7.

**Step 5 — Export as STIX Bundle.** Navigate to `http://localhost:8000/api/stix/bundle?pretty=true`. The bundle contains all correlated objects — jamming zone, military aircraft, camera anomalies — structured for SIEM ingestion.

### Confidence Assessment

| Signals Corroborated | Confidence |
|---------------------|------------|
| 1 source only | Unconfirmed — do not report |
| 2 independent sources | Low confidence — note for monitoring |
| 3+ independent sources | High confidence — reportable finding |

---

## 11. Suggested Next Contributions

### High Impact

| Contribution | Description |
|-------------|-------------|
| Fix WSDOT/TxDOT/Nevada seed IDs | The live APIs for these states have changed endpoints. Finding confirmed working camera IDs from their current APIs and updating the seed lists in `usa_cctv.py` would restore live images for those states. |
| Expand DGT camera list | The confirmed pattern `infocar.dgt.es/etraffic/data/camaras/{id}.jpg` works for many IDs. A probe script that finds all valid IDs would expand Spain coverage to hundreds of cameras. |
| Add SCT Catalonia feed | Servei Català de Trànsit publishes camera data on `transit.gencat.cat`. Covers Barcelona motorways excluded from the national DGT feed. |
| TAXII 2.1 server endpoint | Add `/taxii/` routes so SIEMs can poll Shadowbroker as a proper TAXII server. |
| YOLOv8 camera analysis | The current pixel change detection cannot distinguish a military convoy from a traffic accident. A lightweight YOLOv8 model trained on baseline traffic frames would add semantic understanding to the alert pipeline. |

### Medium Impact

- `CHANGELOG.md` — track version history properly
- GitHub Actions CI — `ruff` lint on Python, `tsc --noEmit` on TypeScript, runs on every PR
- Camera freshness indicator — flag cameras whose `last_updated` is more than 30 minutes old

---

## 12. Legal Status of All Data Sources

| Source | License | API Key | Attribution |
|--------|---------|---------|-------------|
| Madrid City Hall cameras | Madrid Open Data — free reuse with attribution | None | Yes |
| DGT Spain cameras | Ley 37/2007, EU PSI Directive 2019/1024 | None | Yes |
| WSDOT Washington State | WA State DOT public data | None | Yes |
| Virginia DOT (511VA) | VA DOT open data — free with registration | Free | Yes |
| TxDOT Texas | TX DOT public data | None | Yes |
| Nevada/Utah DOT | State DOT public data | None | Yes |
| Florida DOT (fl511) | FL DOT public data | None | Yes |
| Caltrans California | CA DOT public data | None | Yes |
| Georgia DOT (511GA) | GA DOT public data | None | Yes |
| TfL JamCams | Transport for London Open Data | None | Yes |
| NYC DOT | NYC Open Data | None | Yes |
| Austin TxDOT | City of Austin Open Data | None | Yes |
| Singapore LTA | Singapore Government Open Data | Free | Yes |
| OpenSky Network | CC BY 4.0 — free for non-commercial use | Optional | Yes |
| adsb.lol | Public, free | None | Recommended |
| USGS Earthquakes | US Government open data, public domain | None | None |
| GDELT Project | Open, free for all uses | None | Recommended |
| aisstream.io | Free tier available | Required | Yes |

> Shadowbroker is an educational and research tool built entirely on publicly available OSINT data. No classified, restricted, or non-public data sources are used.

---

## 13. Quick Reference

### Common Commands

| Task | Command |
|------|---------|
| Start backend | `cd backend` → `venv\Scripts\activate` → `python main.py` |
| Start frontend | `cd frontend` → `npm run dev` |
| Check camera count | `python -c "import sqlite3; c=sqlite3.connect('cctv.db'); print(c.execute('SELECT source_agency, COUNT(*) FROM cameras GROUP BY source_agency').fetchall())"` |
| Force full refresh | `http://localhost:8000/api/refresh` |
| View STIX bundle | `http://localhost:8000/api/stix/bundle?pretty=true` |
| Health check | `http://localhost:8000/api/health` |

### Git Workflow (PowerShell)

```powershell
git checkout -b feature/your-feature-name
git add backend\services\your_file.py
git commit -m "feat: description of what you added"
git push origin feature/your-feature-name
```

Then open `https://github.com/YOUR_USERNAME/Shadowbroker` and click **Compare & pull request**.

---

## 14. Extended Documentation

### Shadowbroker Contributor & Setup Guide

**[→ Open Document](https://docs.google.com/document/d/1thuyugdJcIwoHI_tWDaA_mUvBE1rfDEd/edit)**

Covers Python installation, all dependency installs, `.env` setup, every error encountered during development with exact cause and fix, and daily startup reference.

### Shadowbroker Analyst Walkthrough

**[→ Open Document](https://docs.google.com/document/d/1qN1n9tduXmX_q46Vy9ZVb_E2EV1lHgXF/edit?usp=sharing)**

Step-by-step guide for using the platform as an intelligence analyst: GPS jamming detection, cross-referencing military aircraft, reading GDELT tone scores, using CCTV cameras for ground truth, and exporting STIX bundles for SIEM ingestion.

---

*Contributed by [Alborz Nazari](https://github.com/AlborzNazari) — [Open Intelligence Lab](https://github.com/AlborzNazari/open-intelligence-lab)*
