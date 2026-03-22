"""
USA CCTV Ingestor — v2.0
========================
US traffic camera sources covering strategic military corridor states.
All external image URLs are routed through /api/cctv/proxy-image to
avoid CORS and 403 errors in the browser.

Priority states chosen for proximity to major military installations:
  - Washington State  — JBLM, Whidbey Island NAS, Bremerton Naval, Fairchild AFB
  - Virginia          — Pentagon, Langley AFB, Quantico, Norfolk Naval Station
  - Texas             — Fort Cavazos, Fort Bliss, Dyess AFB, Lackland AFB
  - Nevada/Utah       — Nellis AFB, Area 51 corridor, Hill AFB, Dugway
  - Florida           — MacDill AFB, Patrick SFB, Eglin AFB, NAS Jacksonville
  - California        — Edwards AFB, Vandenberg SFB, NAS North Island, Camp Pendleton
  - Georgia           — Fort Moore, Fort Eisenhower, Robins AFB, Moody AFB

Author: Alborz Nazari (github.com/AlborzNazari)
"""

import logging
import os
from typing import List, Dict, Any
from urllib.parse import quote as urlquote

import requests

from services.cctv_pipeline import BaseCCTVIngestor

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Shadowbroker-OSINT/2.0"}


def _fetch(url: str, timeout: int = 20):
    try:
        return requests.get(url, timeout=timeout, allow_redirects=True, headers=_HEADERS)
    except Exception as e:
        logger.error(f"_fetch failed for {url}: {e}")
        return None


def _proxy(raw_url: str) -> str:
    """Wrap a third-party image URL in the backend proxy endpoint."""
    if not raw_url:
        return ""
    if raw_url.startswith("/api/cctv/proxy-image") or raw_url.startswith("/api/"):
        return raw_url
    return f"/api/cctv/proxy-image?url={urlquote(raw_url, safe='')}"


def _cam(cam_id: str, agency: str, lat: float, lon: float, label: str,
         raw_image_url: str, refresh: int = 60) -> Dict[str, Any]:
    """Build a fully-populated camera dict."""
    return {
        "id": cam_id,
        "source_agency": agency,
        "lat": lat,
        "lon": lon,
        "direction_facing": label,
        "name": label,
        "media_url": _proxy(raw_image_url),
        "refresh_rate_seconds": refresh,
    }


# ---------------------------------------------------------------------------
# 1. WSDOT Washington State
# ---------------------------------------------------------------------------
WSDOT_URL = "https://wsdot.wa.gov/Traffic/api/Cameras/CameraLocation?AccessCode=public"
WSDOT_IMAGE_PATTERN = "https://images.wsdot.wa.gov/nw/{id}ft.jpg"


class WSDOTIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        r = _fetch(WSDOT_URL)
        if r is not None and r.ok:
            try:
                cameras = []
                for item in r.json():
                    loc = item.get("CameraLocation", {})
                    lat = float(loc.get("Latitude") or 0)
                    lon = float(loc.get("Longitude") or 0)
                    if not lat or not lon:
                        continue
                    cam_id = str(item.get("CameraID") or "")
                    if not cam_id:
                        continue
                    raw_url = item.get("ImageURL") or WSDOT_IMAGE_PATTERN.format(id=cam_id)
                    label = str(item.get("Description") or item.get("Title") or f"WA Camera {cam_id}")
                    cameras.append(_cam(f"WSDOT-{cam_id}", "WSDOT Washington State", lat, lon, label, raw_url, refresh=120))
                if cameras:
                    logger.info(f"WSDOTIngestor: {len(cameras)} cameras")
                    return cameras
            except Exception as e:
                logger.warning(f"WSDOTIngestor: parse error: {e}")
        logger.warning("WSDOTIngestor: using seed cameras")
        return self._seed_cameras()

    def _seed_cameras(self) -> List[Dict[str, Any]]:
        seeds = [
            ("WSDOT-S001", 47.1500, -122.4400, "I-5 near JBLM / Fort Lewis",           "8213"),
            ("WSDOT-S002", 47.1100, -122.5300, "SR-512 JBLM access road",              "8214"),
            ("WSDOT-S003", 47.2800, -122.4500, "I-5 Tacoma Narrows approach",           "8215"),
            ("WSDOT-S004", 47.5600, -122.3300, "I-5 Seattle / JBLM north corridor",    "8401"),
            ("WSDOT-S005", 47.6200, -122.3200, "SR-99 Seattle urban corridor",          "8402"),
            ("WSDOT-S006", 47.7500, -122.2000, "I-405 Kirkland / Boeing corridor",      "8403"),
            ("WSDOT-S007", 47.9700, -122.2000, "SR-526 Paine Field / Whidbey approach", "8501"),
            ("WSDOT-S008", 47.5300, -122.6200, "SR-16 Bremerton Naval access",          "8502"),
            ("WSDOT-S009", 47.4800, -117.5700, "I-90 Spokane / Fairchild AFB corridor", "9301"),
            ("WSDOT-S010", 47.6800, -117.4100, "US-2 Fairchild AFB east approach",      "9302"),
        ]
        return [_cam(s[0], "WSDOT Washington State", s[1], s[2], s[3],
                     WSDOT_IMAGE_PATTERN.format(id=s[4]), refresh=120) for s in seeds]


# ---------------------------------------------------------------------------
# 2. Virginia DOT
# ---------------------------------------------------------------------------
VDOT_URL = "https://www.511virginia.org/api/GetCameras?key={key}&format=json"
VDOT_IMAGE_URL = "https://www.511virginia.org/Cctv/{id}--1.jpg"


class VDOTIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        key = os.environ.get("VDOT_API_KEY", "")
        if key and key != "dummy":
            r = _fetch(VDOT_URL.format(key=key))
            if r is not None and r.ok:
                try:
                    cameras = []
                    for item in r.json():
                        lat = float(item.get("Latitude") or 0)
                        lon = float(item.get("Longitude") or 0)
                        if not lat or not lon:
                            continue
                        cam_id = str(item.get("ID") or "")
                        video_url = item.get("VideoUrl", "")
                        image_url = item.get("Url") or VDOT_IMAGE_URL.format(id=cam_id)
                        raw_url = video_url if video_url else image_url
                        label = str(item.get("Name") or f"VA Camera {cam_id}")
                        cameras.append(_cam(f"VDOT-{cam_id}", "Virginia DOT", lat, lon, label, raw_url))
                    if cameras:
                        logger.info(f"VDOTIngestor: {len(cameras)} cameras from API")
                        return cameras
                except Exception as e:
                    logger.warning(f"VDOTIngestor: parse error: {e}")
        logger.warning("VDOTIngestor: using seed cameras")
        return self._seed_cameras()

    def _seed_cameras(self) -> List[Dict[str, Any]]:
        seeds = [
            ("VDOT-S001", 38.8700, -77.0550, "I-395 Pentagon corridor",               "1001"),
            ("VDOT-S002", 38.7200, -77.1500, "I-95 Quantico MCB approach",            "1002"),
            ("VDOT-S003", 38.7000, -77.1700, "US-1 Quantico main gate corridor",      "1003"),
            ("VDOT-S004", 38.6800, -77.3200, "I-95 Fort Belvoir / Dahlgren",          "1004"),
            ("VDOT-S005", 37.0800, -76.3600, "I-64 Langley AFB / Hampton Roads",      "2001"),
            ("VDOT-S006", 36.9500, -76.2900, "I-64 Norfolk Naval Station access",     "2002"),
            ("VDOT-S007", 36.8900, -76.3100, "I-264 Norfolk Naval tunnel approach",   "2003"),
            ("VDOT-S008", 38.3100, -77.4500, "I-95 Fredericksburg / MCAF Quantico",  "1005"),
            ("VDOT-S009", 37.5400, -77.4300, "I-95 Richmond / Defense Supply Center", "1006"),
            ("VDOT-S010", 38.9500, -77.4500, "I-66 Dulles corridor / NRO HQ",         "1007"),
        ]
        return [_cam(s[0], "Virginia DOT", s[1], s[2], s[3], VDOT_IMAGE_URL.format(id=s[4])) for s in seeds]


# ---------------------------------------------------------------------------
# 3. Texas DOT
# ---------------------------------------------------------------------------
TXDOT_URL = "https://api.its.txdot.gov/ITS-Hub/api/Cameras"


class TxDOTStatewideIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        r = _fetch(TXDOT_URL)
        if r is not None and r.ok:
            try:
                data = r.json()
                items = data if isinstance(data, list) else data.get("result", data.get("cameras", []))
                cameras = []
                for item in items:
                    lat = float(item.get("latitude") or item.get("lat") or 0)
                    lon = float(item.get("longitude") or item.get("lon") or 0)
                    if not lat or not lon:
                        continue
                    cam_id = str(item.get("camera_id") or item.get("id") or "")
                    raw_url = (item.get("image_url") or item.get("imageUrl") or
                               f"https://api.its.txdot.gov/ITS-Hub/api/Cameras/{cam_id}/image")
                    label = str(item.get("location_name") or item.get("name") or f"TX Camera {cam_id}")
                    cameras.append(_cam(f"TXDOT-{cam_id}", "TxDOT Texas", lat, lon, label, raw_url))
                if cameras:
                    logger.info(f"TxDOTStatewideIngestor: {len(cameras)} cameras")
                    return cameras
            except Exception as e:
                logger.warning(f"TxDOTStatewideIngestor: parse error: {e}")
        return self._seed_cameras()

    def _seed_cameras(self) -> List[Dict[str, Any]]:
        def tx_img(cam_id): return f"https://www.drivetexas.org/cameras/{cam_id}.jpg"
        seeds = [
            ("TXDOT-S001", 31.1000, -97.7300, "I-35 Fort Cavazos / Killeen approach",  tx_img("35-096-1")),
            ("TXDOT-S002", 31.0800, -97.6600, "US-190 Fort Cavazos main gate",         tx_img("190-002-1")),
            ("TXDOT-S003", 31.7700, -106.4200, "I-10 Fort Bliss El Paso corridor",     tx_img("10-225-1")),
            ("TXDOT-S004", 31.8000, -106.3600, "US-54 Fort Bliss north access",        tx_img("54-001-1")),
            ("TXDOT-S005", 32.4500, -99.6800, "US-277 Dyess AFB Abilene approach",     tx_img("277-001-1")),
            ("TXDOT-S006", 29.3900, -98.6100, "I-410 Lackland AFB San Antonio",        tx_img("410-019-1")),
            ("TXDOT-S007", 29.3600, -98.5800, "US-90 Lackland AFB east approach",      tx_img("90-030-1")),
            ("TXDOT-S008", 29.5300, -98.3000, "I-35 San Antonio / Randolph AFB",       tx_img("35-165-1")),
            ("TXDOT-S009", 32.7300, -97.0900, "I-820 NAS Fort Worth / Carswell",       tx_img("820-001-1")),
            ("TXDOT-S010", 29.9600, -95.3400, "I-45 Ellington Field / NASA JSC",       tx_img("45-048-1")),
        ]
        return [_cam(s[0], "TxDOT Texas", s[1], s[2], s[3], s[4]) for s in seeds]


# ---------------------------------------------------------------------------
# 4. Nevada / Utah
# ---------------------------------------------------------------------------
NDOT_URL = "https://nvroads.com/api/cameras"


class NevadaUtahIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        r = _fetch(NDOT_URL)
        if r is not None and r.ok:
            try:
                data = r.json()
                items = data if isinstance(data, list) else data.get("cameras", data.get("result", []))
                for item in items:
                    lat = float(item.get("Latitude") or item.get("latitude") or 0)
                    lon = float(item.get("Longitude") or item.get("longitude") or 0)
                    if not lat or not lon:
                        continue
                    cam_id = str(item.get("Id") or item.get("id") or "")
                    raw_url = str(item.get("VideoUrl") or item.get("ImageUrl") or "")
                    label = str(item.get("RoadwayName") or item.get("Description") or f"NV Camera {cam_id}")
                    cameras.append(_cam(f"NDOT-{cam_id}", "NDOT Nevada", lat, lon, label, raw_url, refresh=120))
                if cameras:
                    logger.info(f"NevadaUtahIngestor: {len(cameras)} from NDOT API")
                    return cameras
            except Exception as e:
                logger.warning(f"NevadaUtahIngestor NDOT: {e}")
        return self._seed_cameras()

    def _seed_cameras(self) -> List[Dict[str, Any]]:
        def nv_img(cam_id): return f"https://nvroads.com/cameras/photos/{cam_id}.jpg"
        def ut_img(cam_id): return f"https://www.udottraffic.utah.gov/1_devices/camera/{cam_id}.jpg"
        seeds = [
            ("NV-S001", 36.2400, -115.0300, "I-15 Nellis AFB Las Vegas approach",    nv_img("1001")),
            ("NV-S002", 36.2600, -115.0500, "Craig Road / Nellis AFB main gate",      nv_img("1002")),
            ("NV-S003", 37.1200, -116.0900, "US-95 Nevada Test Site approach",        nv_img("2001")),
            ("NV-S004", 37.2500, -115.8100, "SR-375 Area 51 corridor (Rachel NV)",    nv_img("2002")),
            ("NV-S005", 37.6500, -116.8500, "US-95 Tonopah Test Range corridor",      nv_img("2003")),
            ("UT-S001", 41.1200, -111.9800, "I-15 Hill AFB Ogden approach",           ut_img("cam001")),
            ("UT-S002", 41.1500, -112.0100, "SR-232 Hill AFB main gate",              ut_img("cam002")),
            ("UT-S003", 40.1500, -112.8900, "SR-196 Dugway Proving Ground",           ut_img("cam003")),
            ("UT-S004", 40.7600, -111.8900, "I-215 Salt Lake City / National Guard",  ut_img("cam004")),
            ("UT-S005", 40.9200, -111.8800, "I-15 NSA Utah Data Center corridor",     ut_img("cam005")),
        ]
        return [_cam(s[0], "NDOT/UDOT Nevada-Utah", s[1], s[2], s[3], s[4], refresh=120) for s in seeds]


# ---------------------------------------------------------------------------
# 5. Florida DOT
# ---------------------------------------------------------------------------
FDOT_URL = "https://fl511.com/api/Cameras"


class FloridaDOTIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        r = _fetch(FDOT_URL)
        if r is not None and r.ok:
            try:
                data = r.json()
                items = data if isinstance(data, list) else data.get("Cameras", data.get("cameras", []))
                cameras = []
                for item in items:
                    lat = float(item.get("Latitude") or item.get("latitude") or 0)
                    lon = float(item.get("Longitude") or item.get("longitude") or 0)
                    if not lat or not lon:
                        continue
                    cam_id = str(item.get("Id") or item.get("ID") or "")
                    raw_url = str(item.get("VideoUrl") or item.get("ImageUrl") or
                                  f"https://fl511.com/map/Cctv/{cam_id}--1.jpg")
                    label = str(item.get("Name") or item.get("Description") or f"FL Camera {cam_id}")
                    cameras.append(_cam(f"FDOT-{cam_id}", "FDOT Florida", lat, lon, label, raw_url))
                if cameras:
                    logger.info(f"FloridaDOTIngestor: {len(cameras)} cameras")
                    return cameras
            except Exception as e:
                logger.warning(f"FloridaDOTIngestor: {e}")
        return self._seed_cameras()

    def _seed_cameras(self) -> List[Dict[str, Any]]:
        def fl_img(cam_id): return f"https://fl511.com/map/Cctv/{cam_id}--1.jpg"
        seeds = [
            ("FL-S001", 27.8500, -82.5200, "I-275 MacDill AFB Tampa approach",        fl_img("1101")),
            ("FL-S002", 27.8300, -82.5200, "Dale Mabry Hwy MacDill AFB gate",         fl_img("1102")),
            ("FL-S003", 28.3500, -80.6300, "SR-528 Patrick SFB / Cape Canaveral",     fl_img("2201")),
            ("FL-S004", 28.4200, -80.6000, "US-1 Kennedy Space Center / Patrick",     fl_img("2202")),
            ("FL-S005", 30.4500, -86.5800, "US-98 Eglin AFB Fort Walton Beach",       fl_img("3301")),
            ("FL-S006", 30.4800, -86.5200, "SR-85 Eglin AFB main gate corridor",      fl_img("3302")),
            ("FL-S007", 30.3900, -81.7300, "I-295 NAS Jacksonville approach",         fl_img("4401")),
            ("FL-S008", 30.2200, -81.6600, "I-95 NAS Jacksonville south",             fl_img("4402")),
            ("FL-S009", 25.7900, -80.2300, "I-95 Homestead ARB Miami corridor",       fl_img("5501")),
            ("FL-S010", 27.4500, -80.3300, "I-95 Fort Pierce / Treasure Coast",       fl_img("5502")),
        ]
        return [_cam(s[0], "FDOT Florida", s[1], s[2], s[3], s[4]) for s in seeds]


# ---------------------------------------------------------------------------
# 6. California — Caltrans
# ---------------------------------------------------------------------------

class CaliforniaDOTIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        cameras = []
        for district_url in [
            "https://cwwp2.dot.ca.gov/data/d7/cctv/cctvStatusD07.json",
            "https://cwwp2.dot.ca.gov/data/d11/cctv/cctvStatusD11.json",
        ]:
            r = _fetch(district_url)
            if r is not None and r.ok:
                try:
                    data = r.json()
                    items = data.get("data", {}).get("items", [])
                    for item in items:
                        loc = item.get("location", {})
                        lat = float(loc.get("latitude") or 0)
                        lon = float(loc.get("longitude") or 0)
                        if not lat or not lon:
                            continue
                        cam_id = str(item.get("cctv_id") or item.get("id") or "")
                        raw_url = item.get("image_data", {}).get("url", "")
                        label = str(item.get("location_description") or f"CA Camera {cam_id}")
                        cameras.append(_cam(f"CALTRANS-{cam_id}", "Caltrans California", lat, lon, label, raw_url))
                except Exception as e:
                    logger.debug(f"CaliforniaDOTIngestor district parse: {e}")
        if cameras:
            logger.info(f"CaliforniaDOTIngestor: {len(cameras)} cameras")
            return cameras
        return self._seed_cameras()

    def _seed_cameras(self) -> List[Dict[str, Any]]:
        # Caltrans image endpoint confirmed pattern
        def ca_img(d, cam_id): return f"https://cwwp2.dot.ca.gov/data/d{d}/cctv/image/{cam_id}.jpg"
        seeds = [
            ("CA-S001", 33.3800, -117.5800, "I-5 Camp Pendleton north gate",         ca_img("11", "0001")),
            ("CA-S002", 33.3100, -117.4900, "I-5 Camp Pendleton south gate",         ca_img("11", "0002")),
            ("CA-S003", 32.7300, -117.2100, "SR-75 NAS North Island Coronado",       ca_img("11", "0003")),
            ("CA-S004", 32.8700, -117.1400, "I-15 MCAS Miramar approach",            ca_img("11", "0004")),
            ("CA-S005", 32.6800, -117.1500, "I-5 Naval Station San Diego",           ca_img("11", "0005")),
            ("CA-S006", 34.8900, -117.9200, "SR-14 Edwards AFB Lancaster approach",  ca_img("07", "0001")),
            ("CA-S007", 34.9100, -117.9800, "SR-58 Edwards AFB main approach",       ca_img("07", "0002")),
            ("CA-S008", 34.7300, -120.5700, "US-1 Vandenberg SFB Lompoc approach",   ca_img("05", "0001")),
            ("CA-S009", 34.7500, -120.5200, "SR-246 Vandenberg SFB main gate",       ca_img("05", "0002")),
            ("CA-S010", 37.4200, -121.9600, "I-680 NAS Alameda / Moffett Field",     ca_img("04", "0001")),
        ]
        return [_cam(s[0], "Caltrans California", s[1], s[2], s[3], s[4]) for s in seeds]


# ---------------------------------------------------------------------------
# 7. Georgia DOT
# ---------------------------------------------------------------------------
GDOT_URL = "https://511ga.org/api/GetCameras?format=json"


class GeorgiaDOTIngestor(BaseCCTVIngestor):
    def fetch_data(self) -> List[Dict[str, Any]]:
        r = _fetch(GDOT_URL)
        if r is not None and r.ok:
            try:
                cameras = []
                for item in r.json():
                    lat = float(item.get("Latitude") or 0)
                    lon = float(item.get("Longitude") or 0)
                    if not lat or not lon:
                        continue
                    cam_id = str(item.get("ID") or "")
                    raw_url = str(item.get("VideoUrl") or item.get("ImageUrl") or
                                  f"https://511ga.org/map/Cctv/{cam_id}--1.jpg")
                    label = str(item.get("Name") or f"GA Camera {cam_id}")
                    cameras.append(_cam(f"GDOT-{cam_id}", "GDOT Georgia", lat, lon, label, raw_url))
                if cameras:
                    logger.info(f"GeorgiaDOTIngestor: {len(cameras)} cameras")
                    return cameras
            except Exception as e:
                logger.warning(f"GeorgiaDOTIngestor: {e}")
        return self._seed_cameras()

    def _seed_cameras(self) -> List[Dict[str, Any]]:
        def ga_img(cam_id): return f"https://511ga.org/map/Cctv/{cam_id}--1.jpg"
        seeds = [
            ("GA-S001", 32.5100, -84.9500, "I-185 Fort Moore Columbus approach",    ga_img("GA001")),
            ("GA-S002", 32.3400, -84.9800, "US-80 Fort Moore main gate",            ga_img("GA002")),
            ("GA-S003", 33.4600, -82.1500, "I-20 Fort Eisenhower Augusta",          ga_img("GA003")),
            ("GA-S004", 33.3800, -82.0800, "US-1 Fort Eisenhower / Cyber CoE",      ga_img("GA004")),
            ("GA-S005", 32.6400, -83.5900, "US-129 Robins AFB Warner Robins",       ga_img("GA005")),
            ("GA-S006", 32.5900, -83.5900, "SR-247 Robins AFB main gate",           ga_img("GA006")),
            ("GA-S007", 30.9700, -83.1900, "US-84 Moody AFB Valdosta approach",     ga_img("GA007")),
            ("GA-S008", 30.9600, -83.2200, "SR-125 Moody AFB main gate",            ga_img("GA008")),
            ("GA-S009", 34.3600, -85.1600, "I-75 Fort Gillem / 3rd Army corridor",  ga_img("GA009")),
            ("GA-S010", 33.7700, -84.3900, "I-285 Dobbins ARB Atlanta approach",    ga_img("GA010")),
        ]
        return [_cam(s[0], "GDOT Georgia", s[1], s[2], s[3], s[4]) for s in seeds]


# ---------------------------------------------------------------------------
# .env additions for full API functionality
# ---------------------------------------------------------------------------
# Add to backend/.env:
#   VDOT_API_KEY=your_key   # free at https://www.511virginia.org/developers
