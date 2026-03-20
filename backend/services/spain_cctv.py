"""
Spain CCTV Ingestor
===================
Sources:
  - DGT (Dirección General de Tráfico) — national road cameras via DATEX2 XML
    No API key required. Covers all national roads EXCEPT Basque Country and Catalonia.
    ~500-800 cameras across Spanish motorways and A-roads.

  - Madrid City Hall — urban traffic cameras via open data KML
    No API key required. ~200 cameras across Madrid city centre.

Both sources are published under Spain's open data framework (Ley 37/2007 and
EU PSI Directive 2019/1024). Free reuse with attribution required — source is
credited via source_agency field which surfaces in the Shadowbroker UI.

Author: Alborz Nazari (github.com/AlborzNazari)
"""

import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from services.cctv_pipeline import BaseCCTVIngestor
from services.network_utils import fetch_with_curl

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DGT National Roads — DATEX2 XML
# ---------------------------------------------------------------------------
# Full DATEX2 publication endpoint — no auth required, public open data.
# Returns XML with <cctvCameraRecord> elements containing id, coords, image URL.
# Note: excludes Basque Country (managed by Ertzaintza) and Catalonia (SCT).
DGT_DATEX2_URL = (
    "https://infocar.dgt.es/datex2/dgt/CCTVSiteTablePublication/all/content.xml"
)

# Still image URL pattern — substitute {id} with the camera serial from the XML.
DGT_IMAGE_URL = "https://infocar.dgt.es/etraffic/data/camaras/{id}.jpg"

# DATEX2 namespace used by DGT's XML publication
_NS = {
    "d2": "http://datex2.eu/schema/2/2_0",
}


class DGTNationalIngestor(BaseCCTVIngestor):
    """
    Fetches Spanish national road cameras from DGT's public DATEX2 feed.

    The DATEX2 XML structure looks like:
      <cctvSiteTable>
        <cctvCameraRecord id="...">
          <cctvCameraIdentification>
            <cctvCameraSerialNumber>1234</cctvCameraSerialNumber>
          </cctvCameraIdentification>
          <cctvCameraVehicleDetectionZone>
            <pointCoordinates>
              <latitude>40.416775</latitude>
              <longitude>-3.703790</longitude>
            </pointCoordinates>
          </cctvCameraVehicleDetectionZone>
          <cctvStillImageService>
            <stillImageUrl>https://...</stillImageUrl>
          </cctvStillImageService>
        </cctvCameraRecord>
      </cctvSiteTable>
    """

    def fetch_data(self) -> List[Dict[str, Any]]:
        try:
            response = fetch_with_curl(DGT_DATEX2_URL, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"DGTNationalIngestor: failed to fetch DATEX2 feed: {e}")
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            logger.error(f"DGTNationalIngestor: failed to parse XML: {e}")
            return []

        cameras = []

        # DATEX2 XML may or may not use a namespace prefix depending on the DGT
        # publication version. We try namespaced lookup first, then fall back to
        # a tag-name search that ignores namespaces entirely.
        records = root.findall(".//d2:cctvCameraRecord", _NS)
        if not records:
            # Fallback: namespace-agnostic search
            records = [el for el in root.iter() if el.tag.endswith("cctvCameraRecord")]

        for record in records:
            try:
                cam_id = _find_text(record, "cctvCameraSerialNumber")
                if not cam_id:
                    # Use the XML id attribute as fallback
                    cam_id = record.get("id", "").replace("CAMERA_", "")
                if not cam_id:
                    continue

                lat = _find_text(record, "latitude")
                lon = _find_text(record, "longitude")
                if not lat or not lon:
                    continue

                # Prefer the stillImageUrl from the XML if present,
                # otherwise construct from the known DGT pattern.
                image_url = _find_text(record, "stillImageUrl")
                if not image_url:
                    image_url = DGT_IMAGE_URL.format(id=cam_id)

                # Road/description tag varies across DGT XML versions
                description = (
                    _find_text(record, "locationDescription")
                    or _find_text(record, "roadNumber")
                    or f"DGT Camera {cam_id}"
                )

                cameras.append({
                    "id": f"DGT-{cam_id}",
                    "source_agency": "DGT Spain",
                    "lat": float(lat),
                    "lon": float(lon),
                    "direction_facing": description,
                    "media_url": image_url,
                    "refresh_rate_seconds": 300,  # DGT updates stills every ~5 min
                })

            except (ValueError, TypeError) as e:
                logger.debug(f"DGTNationalIngestor: skipping malformed record: {e}")
                continue

        logger.info(f"DGTNationalIngestor: parsed {len(cameras)} cameras")
        return cameras


# ---------------------------------------------------------------------------
# Madrid City Hall — KML open data
# ---------------------------------------------------------------------------
# Published on datos.madrid.es. KML file with Placemark elements, each containing
# camera location and a description with the image URL.
# Licence: Madrid Open Data (free reuse with attribution).
MADRID_KML_URL = (
    "http://datos.madrid.es/egob/catalogo/202088-0-trafico-camaras.kml"
)

# KML namespace
_KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


class MadridCityIngestor(BaseCCTVIngestor):
    """
    Fetches Madrid City Hall traffic cameras from the datos.madrid.es KML feed.

    KML structure:
      <Placemark>
        <name>Camera name / road</name>
        <Point>
          <coordinates>-3.703790,40.416775,0</coordinates>
        </Point>
        <description><![CDATA[... image URL embedded ...]]></description>
      </Placemark>

    Images are served as snapshots updated every 10 minutes.
    """

    def fetch_data(self) -> List[Dict[str, Any]]:
        try:
            response = fetch_with_curl(MADRID_KML_URL, timeout=20)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"MadridCityIngestor: failed to fetch KML: {e}")
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            logger.error(f"MadridCityIngestor: failed to parse KML: {e}")
            return []

        cameras = []

        # Try namespaced lookup, fall back to tag-name search
        placemarks = root.findall(".//kml:Placemark", _KML_NS)
        if not placemarks:
            placemarks = [el for el in root.iter() if el.tag.endswith("Placemark")]

        for i, placemark in enumerate(placemarks):
            try:
                name_el = _find_element(placemark, "name")
                name = name_el.text.strip() if name_el is not None and name_el.text else f"Madrid Camera {i}"

                coords_el = _find_element(placemark, "coordinates")
                if coords_el is None or not coords_el.text:
                    continue

                # KML coordinates are lon,lat,elevation
                parts = coords_el.text.strip().split(",")
                if len(parts) < 2:
                    continue
                lon = float(parts[0])
                lat = float(parts[1])

                # Madrid KML embeds the image URL inside the description CDATA block.
                # It looks like: <img src="https://...jpg"> or a plain URL.
                # We extract the src attribute value if present.
                desc_el = _find_element(placemark, "description")
                image_url = None
                if desc_el is not None and desc_el.text:
                    image_url = _extract_img_src(desc_el.text)

                if not image_url:
                    # No image available for this placemark — skip it
                    continue

                cameras.append({
                    "id": f"MAD-{i:04d}",
                    "source_agency": "Madrid City Hall",
                    "lat": lat,
                    "lon": lon,
                    "direction_facing": name,
                    "media_url": image_url,
                    "refresh_rate_seconds": 600,  # Madrid updates every 10 min
                })

            except (ValueError, TypeError, IndexError) as e:
                logger.debug(f"MadridCityIngestor: skipping malformed placemark: {e}")
                continue

        logger.info(f"MadridCityIngestor: parsed {len(cameras)} cameras")
        return cameras


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_text(element: ET.Element, tag: str) -> str | None:
    """Find first child element matching tag (ignoring XML namespace) and return its text."""
    el = _find_element(element, tag)
    return el.text.strip() if el is not None and el.text else None


def _find_element(element: ET.Element, tag: str) -> ET.Element | None:
    """Find first descendant element matching tag, ignoring XML namespace prefix."""
    # Try exact match first (no namespace)
    el = element.find(f".//{tag}")
    if el is not None:
        return el
    # Try namespace-agnostic search
    for child in element.iter():
        if child.tag.endswith(f"}}{tag}") or child.tag == tag:
            return child
    return None


def _extract_img_src(html_fragment: str) -> str | None:
    """
    Extract src URL from an <img src="..."> HTML fragment.
    Falls back to finding any http/https URL in the string.
    """
    import re
    # Look for src="..." or src='...'
    match = re.search(r'src=["\']([^"\']+)["\']', html_fragment, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: bare URL
    match = re.search(r'https?://\S+\.jpg', html_fragment, re.IGNORECASE)
    if match:
        return match.group(0)
    return None
