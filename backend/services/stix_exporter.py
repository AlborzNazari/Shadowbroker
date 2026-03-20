"""
STIX 2.1 Exporter for Shadowbroker
====================================
Wraps Shadowbroker's live data into a STIX 2.1 bundle consumable by:
  - Splunk Enterprise Security (TAXII ingest or direct bundle import)
  - Microsoft Sentinel (Threat Intelligence Platforms connector)
  - OpenCTI (STIX2 import connector)
  - IBM QRadar (STIX feed)

Exported object types:
  - Incident       — from GDELT conflict events (geopolitical incidents)
  - Location       — from GPS jamming zones (geographic threat areas)
  - Indicator      — from military flight holding patterns (ISR activity)
  - Relationship   — links Incidents to their Locations

The bundle is served via GET /api/stix/bundle (registered in main.py).
Add ?format=pretty for human-readable JSON during development.

STIX 2.1 spec: https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html

Author: Alborz Nazari (github.com/AlborzNazari)
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# STIX 2.1 identity — identifies Shadowbroker as the producer of this bundle
# ---------------------------------------------------------------------------
SHADOWBROKER_IDENTITY = {
    "type": "identity",
    "spec_version": "2.1",
    "id": "identity--shadowbroker-osint-platform",
    "name": "Shadowbroker OSINT Platform",
    "identity_class": "system",
    "description": (
        "Open-source geospatial intelligence dashboard aggregating public OSINT feeds. "
        "All data derived from publicly available sources. "
        "For research and educational use only."
    ),
    "created": "2026-01-01T00:00:00.000Z",
    "modified": "2026-01-01T00:00:00.000Z",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_stix_bundle(latest_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a complete STIX 2.1 bundle from Shadowbroker's current live data.

    Args:
        latest_data: The dict returned by get_latest_data() from data_fetcher.

    Returns:
        A STIX 2.1 bundle dict, ready to be serialised as JSON.
    """
    objects = [SHADOWBROKER_IDENTITY]

    # GDELT conflict events → STIX Incidents + Locations + Relationships
    gdelt = latest_data.get("gdelt", [])
    incidents, locations, relationships = _gdelt_to_stix(gdelt)
    objects.extend(incidents)
    objects.extend(locations)
    objects.extend(relationships)

    # GPS jamming zones → STIX Locations with x-shadowbroker extension
    jamming = latest_data.get("gps_jamming", [])
    objects.extend(_jamming_to_stix(jamming))

    # Military flight holding patterns → STIX Indicators (ISR activity)
    military = latest_data.get("military_flights", [])
    objects.extend(_military_holding_to_stix(military))

    # Camera anomaly alerts — inject observed-data objects from cctv_alert pipeline
    try:
        from services.cctv_alert import get_active_alerts, alerts_to_stix_objects
        active_alerts = get_active_alerts()
        camera_stix = alerts_to_stix_objects(active_alerts)
        objects.extend(camera_stix)
    except ImportError:
        active_alerts = []
        camera_stix = []
    except Exception as e:
        logger.warning(f"STIX exporter: failed to inject camera alerts: {e}")
        active_alerts = []
        camera_stix = []

    bundle = {
        "type": "bundle",
        "id": f"bundle--{_new_uuid()}",
        "spec_version": "2.1",
        "created": _now(),
        "objects": objects,
    }

    logger.info(
        f"STIX bundle built: {len(incidents)} incidents, "
        f"{len(locations)} locations, {len(relationships)} relationships, "
        f"{len(jamming)} jamming zones, {len(camera_stix)} camera alerts"
    )
    return bundle


# ---------------------------------------------------------------------------
# GDELT → STIX Incidents
# ---------------------------------------------------------------------------

def _gdelt_to_stix(gdelt_features: List[Any]):
    """
    Convert GDELT GeoJSON features into STIX 2.1 Incident + Location objects.

    GDELT features look like:
      {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
          "title": "...",
          "url": "...",
          "date": "...",
          "tone": -3.5,
          "themes": ["MILITARY", "PROTEST", ...],
          "country": "UA"
        }
      }
    """
    incidents = []
    locations = []
    relationships = []

    # GDELT can return a FeatureCollection or a bare list
    if isinstance(gdelt_features, dict) and gdelt_features.get("type") == "FeatureCollection":
        features = gdelt_features.get("features", [])
    elif isinstance(gdelt_features, list):
        features = gdelt_features
    else:
        return incidents, locations, relationships

    for feature in features:
        try:
            props = feature.get("properties", {}) if isinstance(feature, dict) else {}
            geometry = feature.get("geometry", {}) if isinstance(feature, dict) else {}

            title = props.get("title") or props.get("name") or "Unnamed GDELT event"
            event_url = props.get("url", "")
            event_date = props.get("date") or props.get("dateadded") or _now()
            tone = props.get("tone", 0)
            country = props.get("country", "")
            themes = props.get("themes", [])

            # Derive severity from GDELT tone (more negative = more severe)
            severity = _tone_to_severity(tone)

            incident_id = f"incident--{_new_uuid()}"
            incident = {
                "type": "incident",
                "spec_version": "2.1",
                "id": incident_id,
                "created": _now(),
                "modified": _now(),
                "created_by_ref": SHADOWBROKER_IDENTITY["id"],
                "name": title[:256],  # STIX name field max 256 chars
                "description": _build_incident_description(props),
                "first_seen": _normalise_date(event_date),
                "severity": severity,
                "labels": _themes_to_labels(themes),
                "external_references": (
                    [{"source_name": "GDELT", "url": event_url}]
                    if event_url else
                    [{"source_name": "GDELT Project", "url": "https://www.gdeltproject.org"}]
                ),
                "extensions": {
                    "extension-definition--shadowbroker-gdelt": {
                        "extension_type": "property-extension",
                        "gdelt_tone": tone,
                        "gdelt_country": country,
                        "gdelt_themes": themes,
                    }
                },
            }
            incidents.append(incident)

            # Build a STIX Location if we have coordinates
            coords = geometry.get("coordinates", []) if geometry else []
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]
                location_id = f"location--{_new_uuid()}"
                location = {
                    "type": "location",
                    "spec_version": "2.1",
                    "id": location_id,
                    "created": _now(),
                    "modified": _now(),
                    "created_by_ref": SHADOWBROKER_IDENTITY["id"],
                    "name": f"GDELT event location ({country})" if country else "GDELT event location",
                    "latitude": round(lat, 5),
                    "longitude": round(lon, 5),
                    "country": country if len(country) == 2 else "",
                    "precision": 10000,  # GDELT coordinates are city-level, ~10km precision
                }
                locations.append(location)

                # Relationship: incident located-at location
                rel = {
                    "type": "relationship",
                    "spec_version": "2.1",
                    "id": f"relationship--{_new_uuid()}",
                    "created": _now(),
                    "modified": _now(),
                    "created_by_ref": SHADOWBROKER_IDENTITY["id"],
                    "relationship_type": "located-at",
                    "source_ref": incident_id,
                    "target_ref": location_id,
                }
                relationships.append(rel)

        except (KeyError, TypeError, ValueError) as e:
            logger.debug(f"STIX exporter: skipping malformed GDELT feature: {e}")
            continue

    return incidents, locations, relationships


# ---------------------------------------------------------------------------
# GPS Jamming → STIX Locations
# ---------------------------------------------------------------------------

def _jamming_to_stix(jamming_zones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert GPS jamming grid cells into STIX 2.1 Location objects with a
    custom extension carrying severity and affected aircraft count.

    Jamming zone dict from Shadowbroker looks like:
      {
        "lat": 33.5, "lng": 35.2,
        "severity": 67.3,        # percentage of degraded NAC-P readings
        "count": 12              # number of aircraft affected in this cell
      }
    """
    locations = []

    for zone in jamming_zones:
        try:
            lat = zone.get("lat")
            lon = zone.get("lng") or zone.get("lon")
            severity_pct = zone.get("severity", 0)
            affected_count = zone.get("count", 0)

            if lat is None or lon is None:
                continue

            location = {
                "type": "location",
                "spec_version": "2.1",
                "id": f"location--{_new_uuid()}",
                "created": _now(),
                "modified": _now(),
                "created_by_ref": SHADOWBROKER_IDENTITY["id"],
                "name": f"GPS jamming zone ({severity_pct:.0f}% severity)",
                "description": (
                    f"GPS/GNSS interference detected. "
                    f"{affected_count} aircraft showing degraded NAC-P readings. "
                    f"Severity: {severity_pct:.1f}%. "
                    f"Source: Shadowbroker real-time NAC-P analysis."
                ),
                "latitude": round(float(lat), 5),
                "longitude": round(float(lon), 5),
                "precision": 55000,  # Grid cells are ~0.5° ≈ 55km
                "labels": ["gps-jamming", "electronic-warfare", "gnss-interference"],
                "extensions": {
                    "extension-definition--shadowbroker-jamming": {
                        "extension_type": "property-extension",
                        "jamming_severity_pct": round(float(severity_pct), 2),
                        "affected_aircraft_count": int(affected_count),
                        "detection_method": "NAC-P degradation analysis",
                        "data_source": "ADS-B aggregation via adsb.lol",
                    }
                },
            }
            locations.append(location)

        except (TypeError, ValueError) as e:
            logger.debug(f"STIX exporter: skipping malformed jamming zone: {e}")
            continue

    return locations


# ---------------------------------------------------------------------------
# Military holding patterns → STIX Indicators
# ---------------------------------------------------------------------------

def _military_holding_to_stix(military_flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert military flights flagged as holding patterns into STIX 2.1 Indicators.
    Shadowbroker flags holding when total_turn > 300°. These are potential ISR orbits.

    Military flight dict looks like:
      {
        "hex": "AE1234", "flight": "REACH123",
        "lat": 35.5, "lon": 37.2, "alt_baro": 25000,
        "holding": true, "total_turn": 450,
        "type": "RC-135", "desc": "SIGINT aircraft"
      }
    """
    indicators = []

    for flight in military_flights:
        try:
            if not flight.get("holding"):
                continue

            hex_code = flight.get("hex", "UNKNOWN")
            callsign = flight.get("flight", "").strip() or hex_code
            aircraft_type = flight.get("type", "Unknown")
            lat = flight.get("lat")
            lon = flight.get("lon")
            alt = flight.get("alt_baro", 0)
            total_turn = flight.get("total_turn", 0)

            indicator = {
                "type": "indicator",
                "spec_version": "2.1",
                "id": f"indicator--{_new_uuid()}",
                "created": _now(),
                "modified": _now(),
                "created_by_ref": SHADOWBROKER_IDENTITY["id"],
                "name": f"Military holding pattern: {callsign}",
                "description": (
                    f"Military aircraft {callsign} ({aircraft_type}) detected in a "
                    f"holding pattern (total turn: {total_turn:.0f}°). "
                    f"Position: {lat:.3f}°N {lon:.3f}°E at {alt}ft. "
                    f"Possible ISR/reconnaissance orbit. "
                    f"Source: ADS-B via adsb.lol military endpoint."
                ),
                "indicator_types": ["anomalous-activity"],
                "pattern": f"[aircraft:hex_code = '{hex_code}']",
                "pattern_type": "stix",
                "valid_from": _now(),
                "labels": ["military", "holding-pattern", "isr-activity"],
                "extensions": {
                    "extension-definition--shadowbroker-military": {
                        "extension_type": "property-extension",
                        "aircraft_hex": hex_code,
                        "aircraft_type": aircraft_type,
                        "callsign": callsign,
                        "altitude_ft": alt,
                        "total_turn_degrees": round(float(total_turn), 1),
                        "latitude": round(float(lat), 5) if lat else None,
                        "longitude": round(float(lon), 5) if lon else None,
                    }
                },
            }
            indicators.append(indicator)

        except (TypeError, ValueError) as e:
            logger.debug(f"STIX exporter: skipping malformed military flight: {e}")
            continue

    return indicators


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _normalise_date(date_str: str) -> str:
    """Try to parse and reformat a date string to STIX format. Falls back to now."""
    if not date_str:
        return _now()
    try:
        # GDELT dates: YYYYMMDDHHMMSS
        if len(date_str) == 14 and date_str.isdigit():
            dt = datetime.strptime(date_str, "%Y%m%d%H%M%S")
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        # ISO 8601 passthrough
        return date_str if "T" in date_str else date_str + "T00:00:00.000Z"
    except (ValueError, TypeError):
        return _now()


def _tone_to_severity(tone: float) -> str:
    """Map GDELT tone score (negative = bad) to STIX severity vocabulary."""
    if tone <= -10:
        return "high"
    elif tone <= -5:
        return "medium"
    elif tone <= -2:
        return "low"
    return "informational"


def _themes_to_labels(themes: List[str]) -> List[str]:
    """Map GDELT theme strings to lowercase STIX labels (max 10)."""
    if not themes:
        return ["geopolitical-event"]
    return [t.lower().replace("_", "-")[:64] for t in themes[:10]]


def _build_incident_description(props: Dict[str, Any]) -> str:
    """Build a readable description from GDELT event properties."""
    parts = []
    if props.get("title"):
        parts.append(props["title"])
    if props.get("country"):
        parts.append(f"Country: {props['country']}")
    if props.get("tone") is not None:
        parts.append(f"GDELT tone: {props['tone']:.1f}")
    if props.get("themes"):
        parts.append(f"Themes: {', '.join(str(t) for t in props['themes'][:5])}")
    parts.append("Source: GDELT Project (gdeltproject.org). For research use only.")
    return " | ".join(parts)
