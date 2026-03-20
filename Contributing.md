# Contributing to Shadowbroker

> **Global Threat Intercept — Real-Time Geospatial Intelligence Platform**  
> Contributor guide covering installation, Spain CCTV integration, STIX export, and analyst workflow.

---

## Table of Contents

1. [What Is Shadowbroker](#1-what-is-shadowbroker)
2. [How to Contribute](#2-how-to-contribute)
3. [Installation from Scratch](#3-installation-from-scratch)
4. [Running the Platform](#4-running-the-platform)
5. [Spain CCTV Integration](#5-spain-cctv-integration)
6. [STIX 2.1 Export](#6-stix-21-export)
7. [Analyst Walkthrough — Step by Step](#7-analyst-walkthrough--step-by-step)
8. [Suggested Next Contributions](#8-suggested-next-contributions)
9. [Legal Status of All Data Sources](#9-legal-status-of-all-data-sources)
10. [Quick Reference](#10-quick-reference)
11. [Extended Documentation](#11-extended-documentation)

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
| Satellites | N2YO / CelesTrak | ON |
| Earthquakes | USGS real-time feed | ON |
| CCTV Mesh | TfL, NYC, Austin, Singapore, **Spain** | OFF |
| GPS Jamming | NAC-P degradation analysis | ON |
| Ukraine Frontline | DeepState Map GeoJSON | ON |
| Global Incidents | GDELT Project | ON |

---

## 2. How to Contribute

Since you don't have write access, the workflow is:

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

## 3. Installation from Scratch

### 3.1 Prerequisites

| Tool | Where to get it | Verify |
|------|----------------|--------|
| Python 3.10+ | https://python.org — check **Add to PATH** during install | `python --version` |
| Node.js 18+ LTS | https://nodejs.org — use the LTS button | `node --version` |
| Git | https://git-scm.com | `git --version` |

> After installing each tool, **close PowerShell completely and reopen it**. PATH changes only take effect in new terminal sessions.

### 3.2 Clone the Repository

```powershell
cd C:\Users\YourName
git clone https://github.com/AlborzNazari/Shadowbroker.git
cd Shadowbroker
```

### 3.3 Install Backend Dependencies

```powershell
cd backend
pip install -r requirements.txt
npm install ws
```

> `npm install ws` installs the WebSocket library required by the AIS ship tracking proxy.

### 3.4 Install Frontend Dependencies

```powershell
cd ..\frontend
npm install
```

### 3.5 Create the .env File

> **Never commit `.env` to git.** It contains API keys and is already in `.gitignore`.

Run this from the `backend` folder to create a working stub:

```powershell
cd ..\backend
python -c "
with open('.env', 'w', encoding='utf-8') as f:
    f.write('AIS_API_KEY=dummy\n')
    f.write('N2YO_API_KEY=dummy\n')
    f.write('OPENSKY_CLIENT_ID=dummy\n')
    f.write('OPENSKY_CLIENT_SECRET=dummy\n')
print('env created')
"
```

> Dummy values let the server start. For full functionality, register free API keys at [aisstream.io](https://aisstream.io) and [n2yo.com](https://n2yo.com) and replace the dummy values.

---

## 4. Running the Platform

Open **three PowerShell windows** and run one command in each:

**Window 1 — Backend:**
```powershell
cd C:\Users\YourName\Shadowbroker\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Window 2 — Frontend:**
```powershell
cd C:\Users\YourName\Shadowbroker\frontend
npm run dev
```

**Window 3 — Seed Spain cameras (first run only):**
```powershell
cd C:\Users\YourName\Shadowbroker\backend
python -c "
from services.cctv_pipeline import init_db
from services.spain_cctv import DGTNationalIngestor, MadridCityIngestor
init_db()
MadridCityIngestor().ingest()
DGTNationalIngestor().ingest()
print('Done')
"
```

After the first run, cameras are stored in `cctv.db` and reload automatically on each startup.

### Verify Everything Is Running

| What | URL |
|------|-----|
| Live map dashboard | http://localhost:3000 |
| Backend health check | http://localhost:8000/api/health |
| API documentation | http://localhost:8000/docs |
| STIX bundle | http://localhost:8000/api/stix/bundle?pretty=true |
| Raw fast data | http://localhost:8000/api/live-data/fast |
| Raw slow data | http://localhost:8000/api/live-data/slow |

### Common Warnings (Non-Fatal)

| Warning | Cause | Action |
|---------|-------|--------|
| `AIS Stream error: Api Key Is Not Valid` | `.env` has `AIS_API_KEY=dummy` | Get a free key at aisstream.io |
| `Cannot find module 'ws'` | Node ws package missing | Run `npm install ws` in backend folder |
| `Too Many Requests` for stock tickers | Yahoo Finance rate limit | Harmless, retries automatically |
| `UnicodeDecodeError cp1252` | Windows encoding on AIS proxy output | Cosmetic only, no data impact |

---

## 5. Spain CCTV Integration

### 5.1 What Was Added

A new file `backend/services/spain_cctv.py` adds two camera ingestors following the existing `BaseCCTVIngestor` pattern:

| Source | Coverage | Cameras | API Key |
|--------|----------|---------|---------|
| Madrid City Hall (`datos.madrid.es`) | Madrid urban roads and city centre | 357 | None required |
| DGT Spain (`infocar.dgt.es`) | National motorways A-2, A-4, A-6, AP-7 etc. | 20 seed | None required |

### 5.2 What You See on the Map

Enable **CCTV Mesh** from the left panel and zoom into Spain:

- **Green dots clustered across Madrid** — 357 cameras from the Madrid City Hall open data KML feed
- **Green dots along motorways** — DGT national road cameras on A-4, A-6, A-2, AP-7
- **Click any green dot** — opens detail panel with camera name, source, coordinates, and live still image updated every 5–10 minutes
- **At lower zoom levels** — dots cluster into numbered circles, zoom in to see individual cameras

### 5.3 Wiring Into the Scheduler

The Spain ingestors run automatically every 10–15 minutes via `data_fetcher.py`. The relevant additions to `start_scheduler()`:

```python
from services.spain_cctv import DGTNationalIngestor, MadridCityIngestor

_cctv_dgt = DGTNationalIngestor()
_cctv_mad = MadridCityIngestor()

_scheduler.add_job(_cctv_dgt.ingest, 'interval', minutes=10, id='cctv_dgt', max_instances=1, misfire_grace_time=120)
_scheduler.add_job(_cctv_mad.ingest, 'interval', minutes=15, id='cctv_mad', max_instances=1, misfire_grace_time=120)
```

### 5.4 Legality

Both sources are published under Spain's open data framework — **Ley 37/2007** implementing the **EU PSI Directive 2019/1024**. Free reuse with attribution is explicitly permitted. Attribution is satisfied by the `source_agency` field stored in the database and displayed in the UI.

---

## 6. STIX 2.1 Export

### 6.1 What It Does

`backend/services/stix_exporter.py` wraps Shadowbroker's live data into a STIX 2.1 bundle consumable by enterprise SIEMs.

### 6.2 Exported Object Types

| STIX Type | Source Data | What It Represents |
|-----------|-------------|-------------------|
| `incident` | GDELT conflict events | Geopolitical incidents with tone score, country, themes |
| `location` | GPS jamming zones | Geographic interference areas with severity % and aircraft count |
| `indicator` | Military holding patterns | ISR orbit activity — callsign, type, coordinates, turn degrees |
| `relationship` | Auto-generated | Links each incident to its geographic location |

### 6.3 Endpoint

```
GET http://localhost:8000/api/stix/bundle
GET http://localhost:8000/api/stix/bundle?pretty=true
```

### 6.4 Consuming the Bundle

| Platform | How to Consume |
|----------|---------------|
| Splunk Enterprise Security | TAXII feed connector or manual bundle import via threat intelligence manager |
| Microsoft Sentinel | Threat Intelligence Platforms data connector |
| OpenCTI | STIX2 import connector — supports live polling |
| IBM QRadar | STIX/TAXII threat intelligence feed configuration |

---

## 7. Analyst Walkthrough — Step by Step

The value of Shadowbroker is correlation — when multiple independent data sources light up in the same geographic area at the same time.

### Scenario: GPS Jamming Detected Over Spain

---

### Step 1 — Open the Map and Orient Yourself

Navigate to `http://localhost:3000`.

On first load you will see:
- Orange/yellow aircraft icons — commercial and private flights
- Small dots on the ocean — AIS vessel positions
- Colored orbital lines — satellite tracks
- Left panel — layer toggles
- Right panel — search, filters, detail views

> If the map appears blank, the backend is still preloading. Wait 30–60 seconds and refresh.

---

### Step 2 — Check GPS Jamming Zones

Confirm **GPS Jamming** is ON in the left panel. Look for **red square overlays**.

**How jamming is detected:**
- Aircraft broadcast NAC-P (Navigation Accuracy Category for Position) in their ADS-B signal
- NAC-P 0–3 = degraded GPS fix, 8–11 = precise
- When many aircraft in the same grid cell simultaneously show low NAC-P, that cell is flagged
- The percentage label shows severity — `GPS JAM 67%` means 67% of aircraft in that cell are degraded

**What to look for:**
- Red overlays over land near known military bases — likely intentional jamming
- Red overlays near conflict zones — electronic warfare
- Very high percentages (>70%) — widespread, active jamming
- Overlays that appear and disappear quickly — exercise activity

---

### Step 3 — Cross-Reference Military Flights

Ensure **Military Flights** is ON. Look for aircraft near the red overlay.

| Aircraft Type | What It Suggests |
|--------------|-----------------|
| RC-135 Rivet Joint | SIGINT collection — listening to electronic signals in the area |
| E-3 Sentry AWACS | Airborne radar — tracking ground and air movements |
| P-8 Poseidon | Maritime patrol near coastlines |
| RQ-4 Global Hawk | Long-duration ISR — very slow, very high altitude |
| Any holding pattern | Active ISR orbit — Shadowbroker flags when total turn exceeds 300° |

**What to look for:**
- Holding patterns directly above the jamming zone — strong indicator of intentional jamming
- Military callsigns: REACH, FORTE, JAKE, HOMER — US military ISR/transport prefixes
- Aircraft with no callsign — often military or government
- Click any aircraft to see full enrichment data including owner and aircraft type

---

### Step 4 — Enable Spain CCTV Cameras

Toggle **CCTV Mesh** ON. Green dots appear across Spain.

**How to navigate:**
- At national zoom — clustered green circles with numbers, zoom in to break apart
- At city level — individual green dots, one per camera
- Click any dot — detail panel opens with camera name, source, coordinates, live still image
- Images refresh every 5–10 minutes

**What to look for on camera:**
- Unusually light traffic at peak hours — possible road closure or security cordon
- Emergency or military vehicles in frame
- Multiple cameras in same corridor showing identical anomalies simultaneously
- Black or static camera feed — possible deliberate obstruction
- On Madrid urban cameras: police concentration, crowd gatherings, blocked intersections

> DGT cameras cover national motorways — useful for corridor monitoring along A-2, A-4, A-6, AP-7. Madrid cameras cover urban streets.

---

### Step 5 — Check GDELT Global Incidents

Toggle **Global Incidents** ON. Colored markers show conflict and geopolitical events from the last 8 hours.

**How to read GDELT:**
- Each marker = a news event with a geographic coordinate
- Click a marker — see event title, source URL, tone score, themes
- Tone score: negative = conflict/negative coverage, positive = neutral
- Themes: MILITARY, PROTEST, GOVERNMENT, SECURITY, etc.

**What to look for:**
- GDELT events clustered in the same area as your jamming zone
- Events with MILITARY or SECURITY themes in the last 2–4 hours
- Tone scores below -10 — high-conflict reporting
- Multiple events from different sources covering the same location — higher confidence

---

### Step 6 — Rule Out Natural Causes

Check the **Earthquakes** layer and the slow data endpoint for space weather.

Good analyst practice is eliminating innocent explanations before concluding a pattern is significant:
- M4.0+ earthquake near jamming zone — could be environmental GPS interference
- X-class solar flare (check space weather) — can degrade GPS globally
- If jamming is global or very widespread — more likely solar than electronic warfare

---

### Step 7 — Check Maritime Traffic

If the jamming zone is near a coastline, zoom into **AIS Vessels**.

**What to look for:**
- Ships teleporting to unexpected locations — GPS spoof indicator
- Vessels going dark (AIS blackout) in area where traffic is expected
- Carrier Strike Group positions — Shadowbroker tracks all 11 US Navy carriers
- Military vessel icons near the zone — possible naval electronic warfare exercise

---

### Step 8 — Export as STIX Bundle

Navigate to `http://localhost:8000/api/stix/bundle?pretty=true`.

The bundle contains everything Shadowbroker detected, structured for SIEM ingestion:

```json
{
  "type": "bundle",
  "spec_version": "2.1",
  "objects": [
    { "type": "incident",     "...": "GDELT event"           },
    { "type": "location",     "...": "GPS jamming zone"      },
    { "type": "indicator",    "...": "military holding pattern" },
    { "type": "relationship", "...": "incident located-at location" }
  ]
}
```

To share with your team:
- Copy the URL — anyone with network access can pull the live bundle
- Save JSON and import into Splunk ES, Sentinel, or OpenCTI
- Schedule automated polling from your SIEM every 15 minutes

---

### Step 9 — Assess Confidence and Summarize

A finding requires at least **two independent data sources** pointing to the same conclusion.

| Signal | Source | Confidence Weight |
|--------|--------|------------------|
| GPS jamming zone active | NAC-P analysis | Medium alone |
| Military ISR aircraft in holding pattern overhead | Military flights | High when combined |
| Camera shows unusual ground activity | Spain CCTV | High — direct visual |
| GDELT events with military themes in same area | Global Incidents | Medium |
| Ships showing erratic AIS positions nearby | AIS vessels | High — multi-domain confirmation |

> A finding with 3+ corroborating signals from independent layers is **high confidence**. A finding based on a single layer should be flagged as **unconfirmed**.

---

### Layer Quick Reference

| Layer | Normal Appearance | Anomaly Signal |
|-------|-----------------|----------------|
| GPS Jamming | No red overlays | Red square + percentage — investigate aircraft overhead |
| Military Flights | Transit routes, straight lines | Holding pattern flag — possible ISR orbit |
| CCTV Mesh | Normal traffic flow | Dark feed, unusual vehicles, empty roads at peak hours |
| Global Incidents | Sparse markers in stable regions | Cluster of markers with negative tone in same area |
| Earthquakes | Small dots globally | M5.0+ near jamming zone — consider natural cause |
| AIS Vessels | Ships on shipping lanes | Vessels inland, AIS blackout, unusual formation |
| Satellites | Orbital tracks across globe | Military recon satellite pass overhead during event |
| Ukraine Frontline | Stable GeoJSON polygon | Rapid frontline movement correlating with EW signals |

---

## 8. Suggested Next Contributions

### High Impact

| Contribution | Description |
|-------------|-------------|
| Expand DGT camera list | The confirmed image URL `infocar.dgt.es/etraffic/data/camaras/{id}.jpg` works for IDs 1–2000+. A script that probes all IDs and stores valid ones would expand Spain coverage to hundreds of cameras. |
| Add SCT Catalonia feed | Servei Català de Trànsit publishes camera data on `transit.gencat.cat`. Covers the region excluded from the national DGT feed including Barcelona motorways. |
| TAXII 2.1 server endpoint | Add `/taxii/` routes so SIEMs can poll Shadowbroker as a proper TAXII server rather than a plain JSON endpoint. |
| Camera freshness indicator | Flag cameras whose `last_updated` is more than 30 minutes old with a warning indicator in the UI. |
| NaN JSON fix | Add `_safe_float()` sanitizer to `financial.py` to stop `NaN` values breaking the browser JSON parser. |

### Medium Impact

- `CHANGELOG.md` — track version history properly
- GitHub Actions CI — `ruff` lint on Python, `tsc --noEmit` on TypeScript, runs on every PR
- Docker Compose documentation — the `docker-compose.yml` exists but is completely undocumented

---

## 9. Legal Status of All Data Sources

| Source | License | API Key | Attribution Required |
|--------|---------|---------|---------------------|
| Madrid City Hall cameras | Madrid Open Data — free reuse with attribution | None | Yes |
| DGT Spain cameras | Ley 37/2007, EU PSI Directive 2019/1024 | None | Yes |
| OpenSky Network | CC BY 4.0 — free for non-commercial use | Optional | Yes |
| adsb.lol | Public, free | None | Recommended |
| USGS Earthquakes | US Government open data, public domain | None | None |
| GDELT Project | Open, free for all uses | None | Recommended |
| DeepState Map | Public GeoJSON | None | Recommended |
| aisstream.io | Free tier available | Required | Yes |
| N2YO | Free tier — 1000 transactions/hour | Required | Yes |

> Shadowbroker is an educational and research tool built entirely on publicly available OSINT data. No classified, restricted, or non-public data sources are used. All data is consumed and displayed in accordance with each provider's terms of service.

---

## 10. Quick Reference

### Common Commands

| Task | Command |
|------|---------|
| Start backend | `cd backend` then `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload` |
| Start frontend | `cd frontend` then `npm run dev` |
| Seed Spain cameras | `python -c "from services.cctv_pipeline import init_db; from services.spain_cctv import *; init_db(); MadridCityIngestor().ingest(); DGTNationalIngestor().ingest()"` |
| Check Spain camera count | `python -c "from services.cctv_pipeline import get_all_cameras; c=get_all_cameras(); print(len([x for x in c if 'DGT' in x['id'] or 'MAD' in x['id']]))"` |
| View STIX bundle | `http://localhost:8000/api/stix/bundle?pretty=true` |
| Health check | `http://localhost:8000/api/health` |
| Reset a file from git | `python -c "import subprocess; r=subprocess.run(['git','show','main:PATH/file.py'],capture_output=True); open('PATH/file.py','wb').write(r.stdout)"` |

### Git Workflow (PowerShell)

```powershell
git checkout -b feature/your-feature-name
git add backend\services\your_file.py
git commit -m "feat: description of what you added"
git push origin feature/your-feature-name
```

Then open `https://github.com/YOUR_USERNAME/Shadowbroker` and click **Compare & pull request**.

---

## 11. Extended Documentation

Full reference documentation for this contribution is available as two companion guides:

---

### 📘 Shadowbroker Contributor & Setup Guide

**[→ Open Document](https://docs.google.com/document/d/1thuyugdJcIwoHI_tWDaA_mUvBE1rfDEd/edit)**

Covers everything needed to get the platform running from zero on a new Windows machine:

- Python 3.12 installation (why 3.14 breaks, exact installer URL)
- All dependency installs with correct commands for Windows PowerShell
- `.env` file creation without encoding corruption
- Every error encountered during development with exact cause and fix (20+ errors documented)
- CCTV camera seeding and the fetch_cctv slow-tier timing issue
- Daily startup quick reference

---

### 📗 Shadowbroker Analyst Walkthrough

**[→ Open Document](https://docs.google.com/document/d/1qN1n9tduXmX_q46Vy9ZVb_E2EV1lHgXF/edit?usp=sharing)**

Step-by-step guide for using the platform as an intelligence analyst:

- How GPS jamming is detected passively from ADS-B NAC-P values
- Cross-referencing military holding patterns with jamming zones
- Using Spain CCTV cameras for visual ground truth
- Reading GDELT events and tone scores
- Confidence assessment across multiple independent signal layers
- Exporting findings as a STIX 2.1 bundle for SIEM ingestion

---

*Contributed by [Alborz Nazari](https://github.com/AlborzNazari) — [Open Intelligence Lab](https://github.com/AlborzNazari/open-intelligence-lab)*
