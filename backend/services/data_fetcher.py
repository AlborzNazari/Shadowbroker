PATCH — backend/services/data_fetcher.py
========================================
Add to the slow_funcs list in update_slow_data():

    from services.cctv_alert import run_alert_pipeline

    def _run_cctv_alerts():
        """Spatial join + change detection against current live data."""
        from services.fetchers._store import latest_data, _data_lock
        with _data_lock:
            data_snapshot = dict(latest_data)
        run_alert_pipeline(data_snapshot)

Add _run_cctv_alerts to slow_funcs:

    slow_funcs = [
        fetch_news,
        fetch_earthquakes,
        ...
        _run_cctv_alerts,   # <-- ADD THIS LINE
    ]

Also add to start_scheduler() alongside the other CCTV jobs:

    _scheduler.add_job(
        _run_cctv_alerts,
        'interval', minutes=5,
        id='cctv_alerts',
        max_instances=1,
        misfire_grace_time=120
    )

PATCH — backend/services/spain_cctv.py (scheduler wiring)
==========================================================
In data_fetcher.py start_scheduler(), add the new Spain ingestors:

    from services.spain_cctv import (
        DGTNationalIngestor, MadridCityIngestor,
        BarcelonaCityIngestor, ValenciaCityIngestor,
        SevilleCityIngestor, ZaragozaCityIngestor,
        BizkaiaCCTVIngestor, MalagaCityIngestor,
    )

    _cctv_dgt  = DGTNationalIngestor()
    _cctv_mad  = MadridCityIngestor()
    _cctv_bcn  = BarcelonaCityIngestor()
    _cctv_vlc  = ValenciaCityIngestor()
    _cctv_sev  = SevilleCityIngestor()
    _cctv_zgz  = ZaragozaCityIngestor()
    _cctv_biz  = BizkaiaCCTVIngestor()
    _cctv_mal  = MalagaCityIngestor()

    _scheduler.add_job(_cctv_dgt.ingest,  'interval', minutes=10, id='cctv_dgt',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_mad.ingest,  'interval', minutes=15, id='cctv_mad',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_bcn.ingest,  'interval', minutes=10, id='cctv_bcn',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_vlc.ingest,  'interval', minutes=10, id='cctv_vlc',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_sev.ingest,  'interval', minutes=10, id='cctv_sev',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_zgz.ingest,  'interval', minutes=10, id='cctv_zgz',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_biz.ingest,  'interval', minutes=10, id='cctv_biz',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_mal.ingest,  'interval', minutes=10, id='cctv_mal',  max_instances=1, misfire_grace_time=120)

INSTALL — add to requirements.txt if not already present
=========================================================
Pillow>=10.0.0
numpy>=1.24.0
