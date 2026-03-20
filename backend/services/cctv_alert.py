"""
CCTV Alert Pipeline
===================
Connects Shadowbroker's CCTV camera layer to active threat events via:

  1. Spatial Join     — find all cameras within radius_km of active GPS
                        jamming zones and military holding patterns
  2. Change Detection — fetch consecutive still images, compute pixel
                        difference, flag cameras that cross anomaly threshold
  3. STIX Export      — write camera anomalies back as STIX 2.1
                        observed-data objects linked to the triggering event

This module runs as a scheduled background job (every 5 minutes) and
populates two stores:
  - _alert_cache: in-memory list of active camera alerts
  - Injected into stix_exporter.build_stix_bundle() via get_active_alerts()

No computer vision model required. Change detection uses numpy pixel
difference — deployable with zero additional dependencies beyond Pillow
(already in requirements.txt for most Python environments).

Alert types produced:
  CCTV_ANOMALY_NEAR_JAMMING     — camera within radius shows significant
                                   pixel change while a jamming zone is active
  CCTV_ANOMALY_NEAR_HOLDING     — camera near a military ISR holding pattern
  CCTV_BLACKOUT                 — camera that was previously returning images
                                   is now returning a 4xx/5xx or empty response

Author: Alborz Nazari (github.com/AlborzNazari)
"""

import uuid
import math
import logging
import threading
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt to import image processing. Pillow + numpy are lightweight.
# If not installed, change detection gracefully degrades to URL-only alerts.
# ---------------------------------------------------------------------------
try:
    from PIL import Image
    import numpy as np
    _IMAGE_PROCESSING = True
except ImportError:
    _IMAGE_PROCESSING = False
    logger.warning("cctv_alert: Pillow/numpy not available — change detection disabled. "
                   "Run: pip install Pillow numpy")

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ALERT_RADIUS_KM = 25          # cameras within this distance of an event are candidates
CHANGE_THRESHOLD = 0.12       # mean absolute pixel diff / 255 — above this = anomaly
BLACKOUT_THRESHOLD = 3        # consecutive failed fetches before blackout alert fires
IMAGE_RESIZE = (160, 120)     # normalize all images to this size before comparison
MAX_BASELINE_AGE_S = 1800     # baseline image older than 30min is refreshed
MAX_ALERTS_STORED = 200       # cap in-memory alert list

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
_alert_cache: List[Dict[str, Any]] = []
_baseline_store: Dict[str, Dict] = {}   # cam_id -> {array, timestamp}
_failure_counts: Dict[str, int] = {}    # cam_id -> consecutive fetch failures
_alert_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_active_alerts() -> List[Dict[str, Any]]:
    """Return current alert list. Called by stix_exporter to inject into bundle."""
    with _alert_lock:
        return list(_alert_cache)


def clear_alerts():
    """Clear all alerts. Useful for testing."""
    with _alert_lock:
        _alert_cache.clear()


def run_alert_pipeline(latest_data: Dict[str, Any]):
    """
    Main entry point. Called by the scheduler every 5 minutes.

    Args:
        latest_data: dict returned by get_latest_data() from data_fetcher.
    """
    jamming_zones = latest_data.get("gps_jamming", [])
    military_flights = latest_data.get("military_flights", [])

    # Get all cameras from the SQLite store
    try:
        from services.cctv_pipeline import get_all_cameras
        all_cameras = get_all_cameras()
    except Exception as e:
        logger.error(f"cctv_alert: failed to load cameras: {e}")
        return

    if not all_cameras:
        logger.debug("cctv_alert: no cameras in database yet")
        return

    new_alerts: List[Dict[str, Any]] = []

    # --- Pass 1: cameras near active jamming zones ---
    for zone in jamming_zones:
        zone_lat = zone.get("lat")
        zone_lon = zone.get("lng") or zone.get("lon")
        severity = zone.get("severity", 0)
        if zone_lat is None or zone_lon is None:
            continue
        if severity < 20:
            continue  # below 20% severity — not worth alerting

        zone_id = f"JAM-{zone_lat:.3f}-{zone_lon:.3f}"
        nearby = cameras_within_radius(all_cameras, zone_lat, zone_lon, ALERT_RADIUS_KM)

        for cam in nearby:
            alert = _process_camera(
                cam=cam,
                event_id=zone_id,
                event_type="CCTV_ANOMALY_NEAR_JAMMING",
                event_context={
                    "jamming_severity_pct": severity,
                    "jamming_lat": zone_lat,
                    "jamming_lon": zone_lon,
                    "distance_km": round(haversine(zone_lat, zone_lon, cam["lat"], cam["lon"]), 2),
                }
            )
            if alert:
                new_alerts.append(alert)

    # --- Pass 2: cameras near military holding patterns ---
    holding_flights = [f for f in military_flights if f.get("holding")]
    for flight in holding_flights:
        f_lat = flight.get("lat")
        f_lon = flight.get("lon")
        if f_lat is None or f_lon is None:
            continue

        flight_id = f"HOLD-{flight.get('hex', 'UNKNOWN')}"
        nearby = cameras_within_radius(all_cameras, f_lat, f_lon, ALERT_RADIUS_KM)

        for cam in nearby:
            alert = _process_camera(
                cam=cam,
                event_id=flight_id,
                event_type="CCTV_ANOMALY_NEAR_HOLDING",
                event_context={
                    "aircraft_callsign": flight.get("flight", "").strip(),
                    "aircraft_type": flight.get("type", "Unknown"),
                    "aircraft_hex": flight.get("hex", ""),
                    "total_turn_degrees": flight.get("total_turn", 0),
                    "distance_km": round(haversine(f_lat, f_lon, cam["lat"], cam["lon"]), 2),
                }
            )
            if alert:
                new_alerts.append(alert)

    # --- Update alert cache ---
    if new_alerts:
        with _alert_lock:
            _alert_cache.extend(new_alerts)
            # Keep only the most recent MAX_ALERTS_STORED alerts
            if len(_alert_cache) > MAX_ALERTS_STORED:
                _alert_cache[:] = _alert_cache[-MAX_ALERTS_STORED:]

        logger.info(f"cctv_alert: {len(new_alerts)} new alerts generated "
                    f"({len(jamming_zones)} jamming zones, {len(holding_flights)} holding aircraft)")


# ---------------------------------------------------------------------------
# Spatial Functions
# ---------------------------------------------------------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometers between two coordinates."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def cameras_within_radius(
    cameras: List[Dict[str, Any]],
    event_lat: float,
    event_lon: float,
    radius_km: float,
) -> List[Dict[str, Any]]:
    """
    Return all cameras within radius_km of the event coordinate.
    Only cameras with a non-empty media_url are returned — no URL means
    no image to analyze.
    """
    result = []
    for cam in cameras:
        cam_lat = cam.get("lat")
        cam_lon = cam.get("lon")
        media_url = cam.get("media_url", "")
        if cam_lat is None or cam_lon is None or not media_url:
            continue
        dist = haversine(event_lat, event_lon, cam_lat, cam_lon)
        if dist <= radius_km:
            result.append(cam)
    return result


# ---------------------------------------------------------------------------
# Image Fetch and Change Detection
# ---------------------------------------------------------------------------

def _fetch_image_array(url: str) -> Optional["np.ndarray"]:
    """
    Fetch a camera still image URL and return as a normalized numpy array.
    Returns None on any fetch or decode failure.
    Images are converted to grayscale and resized to IMAGE_RESIZE for
    consistent comparison across cameras with different native resolutions.
    """
    if not _IMAGE_PROCESSING or not _REQUESTS_AVAILABLE:
        return None
    try:
        r = _requests.get(
            url, timeout=10,
            headers={"User-Agent": "Shadowbroker-OSINT/2.0"},
            stream=True
        )
        if not r.ok:
            return None
        content = r.content
        if len(content) < 1000:
            return None  # too small to be a real image
        img = Image.open(BytesIO(content)).convert("L")  # grayscale
        img = img.resize(IMAGE_RESIZE, Image.LANCZOS)
        return np.array(img, dtype=np.float32)
    except Exception:
        return None


def _pixel_change_score(frame_a: "np.ndarray", frame_b: "np.ndarray") -> float:
    """
    Compute mean absolute pixel difference between two frames, normalized 0–1.
    0.0 = identical frames. 1.0 = maximum possible difference.

    Thresholds observed in practice:
      < 0.02  lighting change only (time of day, cloud cover)
      0.02–0.08  minor traffic variation, normal
      0.08–0.12  moderate scene change — worth logging
      > 0.12  significant change — anomaly threshold, alert fires
      > 0.30  dramatic change — possible camera obstruction or blackout
    """
    if frame_a.shape != frame_b.shape:
        return 0.0
    diff = np.abs(frame_a - frame_b)
    return float(diff.mean() / 255.0)


def _process_camera(
    cam: Dict[str, Any],
    event_id: str,
    event_type: str,
    event_context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Fetch the camera's current image, compare to baseline, and return
    an alert dict if the change score exceeds CHANGE_THRESHOLD.

    Returns None if:
      - image processing is not available
      - change score is below threshold
      - this is the first fetch (no baseline to compare against)
    """
    cam_id = cam["id"]
    media_url = cam.get("media_url", "")
    if not media_url:
        return None

    now = time.time()
    current_array = _fetch_image_array(media_url)

    # Track fetch failures for blackout detection
    if current_array is None:
        _failure_counts[cam_id] = _failure_counts.get(cam_id, 0) + 1
        if _failure_counts[cam_id] >= BLACKOUT_THRESHOLD:
            logger.warning(f"cctv_alert: camera blackout detected: {cam_id}")
            _failure_counts[cam_id] = 0  # reset after alert
            return _build_alert(
                cam=cam,
                event_id=event_id,
                alert_type="CCTV_BLACKOUT",
                change_score=1.0,
                context={**event_context, "consecutive_failures": BLACKOUT_THRESHOLD},
            )
        return None

    # Successful fetch — reset failure counter
    _failure_counts[cam_id] = 0

    baseline = _baseline_store.get(cam_id)
    baseline_age = now - baseline["timestamp"] if baseline else float("inf")

    # First fetch or stale baseline — store current frame as new baseline
    if baseline is None or baseline_age > MAX_BASELINE_AGE_S:
        _baseline_store[cam_id] = {"array": current_array, "timestamp": now}
        return None  # no comparison possible yet

    # Compare current frame against baseline
    change_score = _pixel_change_score(baseline["array"], current_array)

    # Update baseline with current frame (rolling baseline)
    _baseline_store[cam_id] = {"array": current_array, "timestamp": now}

    if change_score < CHANGE_THRESHOLD:
        return None  # normal variation

    logger.info(
        f"cctv_alert: anomaly detected — {cam_id} change={change_score:.3f} "
        f"event={event_id} type={event_type}"
    )

    return _build_alert(
        cam=cam,
        event_id=event_id,
        alert_type=event_type,
        change_score=change_score,
        context=event_context,
    )


def _build_alert(
    cam: Dict[str, Any],
    event_id: str,
    alert_type: str,
    change_score: float,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a normalized alert dict."""
    return {
        "alert_id": str(uuid.uuid4()),
        "alert_type": alert_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_id": cam["id"],
        "source_agency": cam.get("source_agency", ""),
        "lat": cam.get("lat"),
        "lon": cam.get("lon"),
        "direction_facing": cam.get("direction_facing", ""),
        "media_url": cam.get("media_url", ""),
        "change_score": round(change_score, 4),
        "correlated_event_id": event_id,
        "context": context,
    }


# ---------------------------------------------------------------------------
# STIX 2.1 Serialization
# ---------------------------------------------------------------------------

def alerts_to_stix_objects(alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert alert dicts to STIX 2.1 observed-data objects.
    Called by stix_exporter.build_stix_bundle() to inject camera
    anomalies into the bundle alongside jamming zones and incidents.

    Each alert becomes one observed-data object with a custom
    extension carrying the full camera and change detection metadata.
    The correlated_event_id field links this object to the jamming
    zone or holding pattern that triggered the spatial join.
    """
    objects = []
    for alert in alerts:
        stix_obj = {
            "type": "observed-data",
            "spec_version": "2.1",
            "id": f"observed-data--{uuid.uuid4()}",
            "created": alert["timestamp"],
            "modified": alert["timestamp"],
            "first_observed": alert["timestamp"],
            "last_observed": alert["timestamp"],
            "number_observed": 1,
            "object_refs": [],
            "labels": [
                alert["alert_type"].lower().replace("_", "-"),
                "cctv-change-detection",
                "visual-ground-truth",
            ],
            "extensions": {
                "extension-definition--shadowbroker-cctv-alert": {
                    "extension_type": "property-extension",
                    "alert_type": alert["alert_type"],
                    "camera_id": alert["camera_id"],
                    "source_agency": alert["source_agency"],
                    "latitude": alert["lat"],
                    "longitude": alert["lon"],
                    "direction_facing": alert["direction_facing"],
                    "image_url": alert["media_url"],
                    "change_score": alert["change_score"],
                    "change_threshold_used": CHANGE_THRESHOLD,
                    "correlated_event_id": alert["correlated_event_id"],
                    "context": alert["context"],
                }
            },
        }
        objects.append(stix_obj)
    return objects
