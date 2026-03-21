PATCH — backend/services/data_fetcher.py
========================================
Add after the existing Spain CCTV imports in start_scheduler():

    from services.usa_cctv import (
        WSDOTIngestor, VDOTIngestor, TxDOTStatewideIngestor,
        NevadaUtahIngestor, FloridaDOTIngestor,
        CaliforniaDOTIngestor, GeorgiaDOTIngestor,
    )

    _cctv_wsdot = WSDOTIngestor()
    _cctv_vdot  = VDOTIngestor()
    _cctv_txdot = TxDOTStatewideIngestor()
    _cctv_nvut  = NevadaUtahIngestor()
    _cctv_fdot  = FloridaDOTIngestor()
    _cctv_ca    = CaliforniaDOTIngestor()
    _cctv_gdot  = GeorgiaDOTIngestor()

    _scheduler.add_job(_cctv_wsdot.ingest, 'interval', minutes=10, id='cctv_wsdot', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_vdot.ingest,  'interval', minutes=10, id='cctv_vdot',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_txdot.ingest, 'interval', minutes=10, id='cctv_txdot', max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_nvut.ingest,  'interval', minutes=15, id='cctv_nvut',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_fdot.ingest,  'interval', minutes=10, id='cctv_fdot',  max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_ca.ingest,    'interval', minutes=10, id='cctv_ca',    max_instances=1, misfire_grace_time=120)
    _scheduler.add_job(_cctv_gdot.ingest,  'interval', minutes=10, id='cctv_gdot',  max_instances=1, misfire_grace_time=120)


PATCH — backend/.env (optional — adds VA DOT live cameras)
===========================================================
VDOT_API_KEY=your_key_here
# Register free at: https://www.511virginia.org/developers


SEED COMMAND — run once after copying usa_cctv.py
=================================================
py -3.12 -c "
from services.cctv_pipeline import init_db
from services.usa_cctv import (
    WSDOTIngestor, VDOTIngestor, TxDOTStatewideIngestor,
    NevadaUtahIngestor, FloridaDOTIngestor,
    CaliforniaDOTIngestor, GeorgiaDOTIngestor
)
init_db()
WSDOTIngestor().ingest()
VDOTIngestor().ingest()
TxDOTStatewideIngestor().ingest()
NevadaUtahIngestor().ingest()
FloridaDOTIngestor().ingest()
CaliforniaDOTIngestor().ingest()
GeorgiaDOTIngestor().ingest()
from services.cctv_pipeline import get_all_cameras
cams = get_all_cameras()
usa = [c for c in cams if any(x in c['id'] for x in ['WSDOT','VDOT','TXDOT','NDOT','FDOT','CALTRANS','GDOT'])]
print(f'USA cameras added: {len(usa)}')
print(f'Total all cameras: {len(cams)}')
"
