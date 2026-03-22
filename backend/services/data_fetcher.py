"""Scheduler and coordinator for all background data fetchers.
 
This module owns:
  - start_scheduler / stop_scheduler  (APScheduler lifecycle)
  - update_all_data                   (single full refresh, called by /api/refresh)
  - get_latest_data                   (snapshot for API endpoints)
  - source_timestamps                 (re-exported from _store for main.py)
 
All actual fetch logic lives in services/fetchers/*.py and the CCTV ingestors.
"""
 
import logging
import concurrent.futures
from apscheduler.schedulers.background import BackgroundScheduler
 
from services.fetchers._store import latest_data, source_timestamps, _data_lock
 
# ---------------------------------------------------------------------------
# Fast fetchers (run every 60 s)
# ---------------------------------------------------------------------------
from services.fetchers.flights import fetch_flights
from services.fetchers.military import fetch_military_flights
from services.fetchers.geo import fetch_ships, update_liveuamap
from services.fetchers.satellites import fetch_satellites
 
# ---------------------------------------------------------------------------
# Slow fetchers (run every 30 min)
# ---------------------------------------------------------------------------
from services.fetchers.news import fetch_news
from services.fetchers.financial import fetch_defense_stocks, fetch_oil_prices
from services.fetchers.earth_observation import (
    fetch_earthquakes,
    fetch_firms_fires,
    fetch_space_weather,
    fetch_weather,
)
from services.fetchers.geo import (
    fetch_frontlines,
    fetch_gdelt,
    fetch_airports,
    fetch_geopolitics,
)
from services.fetchers.infrastructure import (
    fetch_internet_outages,
    fetch_datacenters,
    fetch_military_bases,
    fetch_power_plants,
    fetch_cctv,
    fetch_kiwisdr,
)
 
logger = logging.getLogger("services.data_fetcher")
 
_scheduler = BackgroundScheduler(timezone="UTC")
 
# ---------------------------------------------------------------------------
# CCTV ingestor instances (Spain + USA) — initialised once at module load
# ---------------------------------------------------------------------------
from services.spain_cctv import (
    MadridCityIngestor,
    DGTNationalIngestor,
    BarcelonaCityIngestor,
    ValenciaCityIngestor,
    SevilleCityIngestor,
    ZaragozaCityIngestor,
    BizkaiaCCTVIngestor,
    MalagaCityIngestor,
)
 
_cctv_madrid    = MadridCityIngestor()
_cctv_dgt       = DGTNationalIngestor()
_cctv_barcelona = BarcelonaCityIngestor()
_cctv_valencia  = ValenciaCityIngestor()
_cctv_sevilla   = SevilleCityIngestor()
_cctv_zaragoza  = ZaragozaCityIngestor()
_cctv_bizkaia   = BizkaiaCCTVIngestor()
_cctv_malaga    = MalagaCityIngestor()
 
from services.usa_cctv import (
    WSDOTIngestor,
    VDOTIngestor,
    TxDOTStatewideIngestor,
    NevadaUtahIngestor,
    FloridaDOTIngestor,
    CaliforniaDOTIngestor,
    GeorgiaDOTIngestor,
)
 
_cctv_wsdot = WSDOTIngestor()
_cctv_vdot  = VDOTIngestor()
_cctv_txdot = TxDOTStatewideIngestor()
_cctv_nvut  = NevadaUtahIngestor()
_cctv_fdot  = FloridaDOTIngestor()
_cctv_ca    = CaliforniaDOTIngestor()
_cctv_gdot  = GeorgiaDOTIngestor()
 
 
# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
 
def get_latest_data() -> dict:
    """Return a shallow copy of the in-memory data store."""
    with _data_lock:
        return dict(latest_data)
 
 
# ---------------------------------------------------------------------------
# CCTV alert pipeline wrapper — runs every 5 min, feeds live data snapshot
# ---------------------------------------------------------------------------
def _run_cctv_alert_pipeline():
    """Scheduled wrapper: pulls latest snapshot and feeds it to the alert pipeline."""
    try:
        from services.cctv_alert import run_alert_pipeline
        run_alert_pipeline(get_latest_data())
    except Exception as e:
        logger.error(f"cctv_alert pipeline error: {e}")
 
 
def update_all_data():
    """Run every fetcher once, in parallel where safe."""
    logger.info("Running full data update...")
 
    fast_fetchers = [
        fetch_flights,
        fetch_military_flights,
        fetch_ships,
        fetch_satellites,
        update_liveuamap,
    ]
    slow_fetchers = [
        fetch_news,
        fetch_defense_stocks,
        fetch_oil_prices,
        fetch_earthquakes,
        fetch_firms_fires,
        fetch_space_weather,
        fetch_weather,
        fetch_frontlines,
        fetch_gdelt,
        fetch_geopolitics,
        fetch_airports,
        fetch_internet_outages,
        fetch_datacenters,
        fetch_military_bases,
        fetch_power_plants,
        fetch_cctv,
        fetch_kiwisdr,
    ]
 
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): fn.__name__ for fn in fast_fetchers + slow_fetchers}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error(f"{name} raised: {exc}")
 
    logger.info("Full data update complete.")
 
 
def start_scheduler():
    """Register all recurring jobs and start APScheduler."""
 
    # Ensure cctv.db exists before any ingestor or alert job runs
    try:
        from services.cctv_pipeline import init_db
        init_db()
        logger.info("CCTV database initialised.")
    except Exception as e:
        logger.error(f"CCTV DB init failed: {e}")
 
    # --- Fast jobs: every 60 seconds ---
    _scheduler.add_job(fetch_flights,          "interval", seconds=60,  id="flights",    max_instances=1, misfire_grace_time=30)
    _scheduler.add_job(fetch_military_flights, "interval", seconds=60,  id="military",   max_instances=1, misfire_grace_time=30)
    _scheduler.add_job(fetch_ships,            "interval", seconds=60,  id="ships",      max_instances=1, misfire_grace_time=30)
    _scheduler.add_job(fetch_satellites,       "interval", seconds=60,  id="satellites", max_instances=1, misfire_grace_time=30)
    _scheduler.add_job(update_liveuamap,       "interval", seconds=60,  id="liveuamap",  max_instances=1, misfire_grace_time=30)
 
    # --- Slow jobs: every 30 minutes ---
    _scheduler.add_job(fetch_news,              "interval", minutes=30, id="news",               max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_defense_stocks,    "interval", minutes=30, id="stocks",             max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_oil_prices,        "interval", minutes=30, id="oil",                max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_earthquakes,       "interval", minutes=30, id="earthquakes",        max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_firms_fires,       "interval", minutes=30, id="firms_fires",        max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_space_weather,     "interval", minutes=30, id="space_weather",      max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_weather,           "interval", minutes=30, id="weather",            max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_frontlines,        "interval", minutes=30, id="frontlines",         max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_gdelt,             "interval", minutes=30, id="gdelt",              max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_geopolitics,       "interval", minutes=30, id="geopolitics",        max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_airports,          "interval", minutes=30, id="airports",           max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_internet_outages,  "interval", minutes=30, id="internet_outages",   max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_datacenters,       "interval", minutes=30, id="datacenters",        max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_military_bases,    "interval", minutes=30, id="military_bases",     max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_power_plants,      "interval", minutes=30, id="power_plants",       max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_kiwisdr,           "interval", minutes=30, id="kiwisdr",            max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(fetch_cctv,              "interval", minutes=10, id="cctv_read",          max_instances=1, misfire_grace_time=120)
 
    # --- CCTV alert pipeline: every 5 minutes ---
    _scheduler.add_job(_run_cctv_alert_pipeline, "interval", minutes=5, id="cctv_alerts", max_instances=1, misfire_grace_time=60)
 
    # --- Spain CCTV ingestors: every 10 minutes ---
    _scheduler.add_job(_cctv_madrid.ingest,    "interval", minutes=10, id="cctv_madrid",    max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_dgt.ingest,       "interval", minutes=10, id="cctv_dgt",       max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_barcelona.ingest, "interval", minutes=10, id="cctv_barcelona", max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_valencia.ingest,  "interval", minutes=10, id="cctv_valencia",  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_sevilla.ingest,   "interval", minutes=10, id="cctv_sevilla",   max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_zaragoza.ingest,  "interval", minutes=10, id="cctv_zaragoza",  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_bizkaia.ingest,   "interval", minutes=10, id="cctv_bizkaia",   max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_malaga.ingest,    "interval", minutes=10, id="cctv_malaga",    max_instances=1, misfire_grace_time=120)
 
    # --- USA CCTV ingestors ---
    _scheduler.add_job(_cctv_wsdot.ingest, "interval", minutes=10, id="cctv_wsdot", max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_vdot.ingest,  "interval", minutes=10, id="cctv_vdot",  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_txdot.ingest, "interval", minutes=10, id="cctv_txdot", max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_nvut.ingest,  "interval", minutes=15, id="cctv_nvut",  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_fdot.ingest,  "interval", minutes=10, id="cctv_fdot",  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_ca.ingest,    "interval", minutes=10, id="cctv_ca",    max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_gdot.ingest,  "interval", minutes=10, id="cctv_gdot",  max_instances=1, misfire_grace_time=120)
 
    _scheduler.start()
    logger.info("APScheduler started with %d jobs.", len(_scheduler.get_jobs()))
 
 
def stop_scheduler():
    """Shut down APScheduler cleanly."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
