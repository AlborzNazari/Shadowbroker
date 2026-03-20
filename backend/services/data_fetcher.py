============================================================
PATCH 1 — backend/services/data_fetcher.py
============================================================

Find this block (around line 110 in start_scheduler):

    from services.cctv_pipeline import (
        TFLJamCamIngestor, LTASingaporeIngestor,
        AustinTXIngestor, NYCDOTIngestor,
    )
    _cctv_tfl = TFLJamCamIngestor()
    _cctv_lta = LTASingaporeIngestor()
    _cctv_atx = AustinTXIngestor()
    _cctv_nyc = NYCDOTIngestor()
    _scheduler.add_job(_cctv_tfl.ingest, 'interval', minutes=10, id='cctv_tfl', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_lta.ingest, 'interval', minutes=10, id='cctv_lta', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_atx.ingest, 'interval', minutes=10, id='cctv_atx', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_nyc.ingest, 'interval', minutes=10, id='cctv_nyc', max_instances=1, misfire_grace_time=120)

REPLACE with (adds two Spain ingestors):

    from services.cctv_pipeline import (
        TFLJamCamIngestor, LTASingaporeIngestor,
        AustinTXIngestor, NYCDOTIngestor,
    )
    from services.spain_cctv import DGTNationalIngestor, MadridCityIngestor

    _cctv_tfl = TFLJamCamIngestor()
    _cctv_lta = LTASingaporeIngestor()
    _cctv_atx = AustinTXIngestor()
    _cctv_nyc = NYCDOTIngestor()
    _cctv_dgt = DGTNationalIngestor()
    _cctv_mad = MadridCityIngestor()

    _scheduler.add_job(_cctv_tfl.ingest, 'interval', minutes=10, id='cctv_tfl', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_lta.ingest, 'interval', minutes=10, id='cctv_lta', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_atx.ingest, 'interval', minutes=10, id='cctv_atx', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_nyc.ingest, 'interval', minutes=10, id='cctv_nyc', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_dgt.ingest, 'interval', minutes=10, id='cctv_dgt', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_mad.ingest, 'interval', minutes=15, id='cctv_mad', max_instances=1, misfire_grace_time=120)


============================================================
PATCH 2 — backend/main.py
============================================================

Find this line near the bottom (before the if __name__ == "__main__": block):

    threading.Timer(2.0, schedule_restart, args=[project_root]).start()
    return result

ADD this entire block AFTER the system_update route and BEFORE if __name__:

    # ---------------------------------------------------------------------------
    # STIX 2.1 Export — threat intelligence interoperability
    # Compatible with Splunk ES, Microsoft Sentinel, OpenCTI, IBM QRadar
    # ---------------------------------------------------------------------------
    from services.stix_exporter import build_stix_bundle
    import json as _json

    @app.get("/api/stix/bundle")
    @limiter.limit("10/minute")
    async def stix_bundle(
        request: Request,
        pretty: bool = Query(False, description="Set true for human-readable JSON"),
    ):
        """
        Returns a STIX 2.1 bundle of current threat intelligence derived from
        Shadowbroker's live data feeds (GDELT incidents, GPS jamming zones,
        military holding patterns).

        Consume this endpoint from:
          - Splunk ES: TAXII/STIX feed or manual bundle import
          - Microsoft Sentinel: Threat Intelligence Platforms data connector
          - OpenCTI: STIX2 import connector
        """
        data = get_latest_data()
        bundle = build_stix_bundle(data)
        indent = 2 if pretty else None
        content = _json.dumps(bundle, indent=indent)
        return Response(
            content=content,
            media_type="application/stix+json",
            headers={"Cache-Control": "no-cache"},
        )
