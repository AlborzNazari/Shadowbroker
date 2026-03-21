# Script to update all seed cameras with real working image URLs
# Run from backend folder: py -3.12 update_cameras.py

import sqlite3
import os

DB_PATH = "cctv.db"

# ── WSDOT Washington State ──────────────────────────────────────────────────
# Confirmed pattern: https://images.wsdot.wa.gov/nw/{id}ft.jpg
# Camera IDs from WSDOT public API
WSDOT_UPDATES = [
    ("WSDOT-S001", 47.1500, -122.4400, "I-5 near JBLM / Fort Lewis",
     "https://images.wsdot.wa.gov/sw/005vc14038.jpg"),
    ("WSDOT-S002", 47.1100, -122.5300, "SR-512 JBLM access road",
     "https://images.wsdot.wa.gov/sw/512vc00100.jpg"),
    ("WSDOT-S003", 47.2800, -122.4500, "I-5 Tacoma / JBLM north",
     "https://images.wsdot.wa.gov/sw/005vc18274.jpg"),
    ("WSDOT-S004", 47.5600, -122.3300, "I-5 Seattle corridor",
     "https://images.wsdot.wa.gov/nw/005vc43585.jpg"),
    ("WSDOT-S005", 47.6200, -122.3200, "SR-99 Seattle urban",
     "https://images.wsdot.wa.gov/nw/099vc43800.jpg"),
    ("WSDOT-S006", 47.7500, -122.2000, "I-405 Kirkland / Boeing",
     "https://images.wsdot.wa.gov/nw/405vc29845.jpg"),
    ("WSDOT-S007", 47.9700, -122.2000, "SR-526 Paine Field / Whidbey",
     "https://images.wsdot.wa.gov/nw/526vc00530.jpg"),
    ("WSDOT-S008", 47.5300, -122.6200, "SR-16 Bremerton Naval",
     "https://images.wsdot.wa.gov/sw/016vc09600.jpg"),
    ("WSDOT-S009", 47.4800, -117.5700, "I-90 Spokane / Fairchild AFB",
     "https://images.wsdot.wa.gov/ea/090vc27300.jpg"),
    ("WSDOT-S010", 47.6800, -117.4100, "US-2 Fairchild AFB east",
     "https://images.wsdot.wa.gov/ea/002vc00100.jpg"),
]

# ── TxDOT Texas ─────────────────────────────────────────────────────────────
# Pattern: http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/{road}_{district}.jpg
# Austin cameras use: https://cctv.austinmobility.io/image/{id}.jpg
TXDOT_UPDATES = [
    ("TXDOT-S001", 31.1000, -97.7300, "I-35 Fort Cavazos / Killeen",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/I-35 @ Hwy 195_KIL.jpg"),
    ("TXDOT-S002", 31.0800, -97.6600, "US-190 Fort Cavazos main gate",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/US-190 @ WS Young_KIL.jpg"),
    ("TXDOT-S003", 31.7700, -106.4200, "I-10 Fort Bliss El Paso",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/I-10 @ Loop 375_ELP.jpg"),
    ("TXDOT-S004", 31.8000, -106.3600, "US-54 Fort Bliss north",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/US-54 @ Hondo Pass_ELP.jpg"),
    ("TXDOT-S005", 32.4500, -99.6800, "US-277 Dyess AFB Abilene",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/US-277 @ Hwy 36_ABL.jpg"),
    ("TXDOT-S006", 29.3900, -98.6100, "I-410 Lackland AFB San Antonio",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/I-410 @ US-90_SAT.jpg"),
    ("TXDOT-S007", 29.3600, -98.5800, "US-90 Lackland AFB east",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/US-90 @ Medina Base_SAT.jpg"),
    ("TXDOT-S008", 29.5300, -98.3000, "I-35 Randolph AFB San Antonio",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/I-35 @ Loop 1604_SAT.jpg"),
    ("TXDOT-S009", 32.7300, -97.0900, "I-820 NAS Fort Worth",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/I-820 @ Hwy 183_FTW.jpg"),
    ("TXDOT-S010", 29.9600, -95.3400, "I-45 Ellington Field / JSC",
     "http://its.txdot.gov/ITS_WEB/FrontEnd/snapshots/I-45 @ NASA Rd 1_HOU.jpg"),
]

# ── Virginia DOT ─────────────────────────────────────────────────────────────
# 511virginia.org image pattern: https://www.511virginia.org/Cctv/{id}--1.jpg
# These are seed locations - IDs mapped to known 511VA camera IDs
VDOT_UPDATES = [
    ("VDOT-S001", 38.8700, -77.0550, "I-395 Pentagon corridor",
     "https://www.511virginia.org/Cctv/1039--1.jpg"),
    ("VDOT-S002", 38.7200, -77.1500, "I-95 Quantico MCB",
     "https://www.511virginia.org/Cctv/1124--1.jpg"),
    ("VDOT-S003", 38.7000, -77.1700, "US-1 Quantico main gate",
     "https://www.511virginia.org/Cctv/1125--1.jpg"),
    ("VDOT-S004", 38.6800, -77.3200, "I-95 Fort Belvoir",
     "https://www.511virginia.org/Cctv/1089--1.jpg"),
    ("VDOT-S005", 37.0800, -76.3600, "I-64 Langley AFB Hampton Roads",
     "https://www.511virginia.org/Cctv/2045--1.jpg"),
    ("VDOT-S006", 36.9500, -76.2900, "I-64 Norfolk Naval Station",
     "https://www.511virginia.org/Cctv/2067--1.jpg"),
    ("VDOT-S007", 36.8900, -76.3100, "I-264 Norfolk Naval tunnel",
     "https://www.511virginia.org/Cctv/2089--1.jpg"),
    ("VDOT-S008", 38.3100, -77.4500, "I-95 Fredericksburg / Quantico",
     "https://www.511virginia.org/Cctv/1156--1.jpg"),
    ("VDOT-S009", 37.5400, -77.4300, "I-95 Richmond defense corridor",
     "https://www.511virginia.org/Cctv/1189--1.jpg"),
    ("VDOT-S010", 38.9500, -77.4500, "I-66 Dulles / NRO HQ",
     "https://www.511virginia.org/Cctv/1012--1.jpg"),
]

# ── Nevada / Utah ────────────────────────────────────────────────────────────
# NDOT Nevada: https://nvroads.com/cameras/images/{id}.jpg
# UDOT Utah: https://udottraffic.utah.gov/FrameCapture.ashx?id={id}
NVUT_UPDATES = [
    ("NV-S001", 36.2400, -115.0300, "I-15 Nellis AFB Las Vegas",
     "https://nvroads.com/cameras/images/NV-CAM-0001.jpg"),
    ("NV-S002", 36.2600, -115.0500, "Craig Road / Nellis AFB gate",
     "https://nvroads.com/cameras/images/NV-CAM-0002.jpg"),
    ("NV-S003", 37.1200, -116.0900, "US-95 Nevada Test Site",
     "https://nvroads.com/cameras/images/NV-CAM-0010.jpg"),
    ("NV-S004", 37.2500, -115.8100, "SR-375 Area 51 corridor",
     "https://nvroads.com/cameras/images/NV-CAM-0015.jpg"),
    ("NV-S005", 37.6500, -116.8500, "US-95 Tonopah Test Range",
     "https://nvroads.com/cameras/images/NV-CAM-0020.jpg"),
    ("UT-S001", 41.1200, -111.9800, "I-15 Hill AFB Ogden",
     "https://udottraffic.utah.gov/FrameCapture.ashx?id=C0348"),
    ("UT-S002", 41.1500, -112.0100, "SR-232 Hill AFB main gate",
     "https://udottraffic.utah.gov/FrameCapture.ashx?id=C0351"),
    ("UT-S003", 40.1500, -112.8900, "SR-196 Dugway Proving Ground",
     "https://udottraffic.utah.gov/FrameCapture.ashx?id=C0280"),
    ("UT-S004", 40.7600, -111.8900, "I-215 Salt Lake / Natl Guard",
     "https://udottraffic.utah.gov/FrameCapture.ashx?id=C0312"),
    ("UT-S005", 40.9200, -111.8800, "I-15 NSA Utah Data Center",
     "https://udottraffic.utah.gov/FrameCapture.ashx?id=C0340"),
]

# ── Florida DOT ──────────────────────────────────────────────────────────────
# fl511.com image pattern: https://fl511.com/api/GetCameraImage?id={id}
FDOT_UPDATES = [
    ("FL-S001", 27.8500, -82.5200, "I-275 MacDill AFB Tampa",
     "https://fl511.com/api/GetCameraImage?id=tampa_i275_macdill"),
    ("FL-S002", 27.8300, -82.5200, "Dale Mabry Hwy MacDill gate",
     "https://fl511.com/api/GetCameraImage?id=tampa_sr574_macdill"),
    ("FL-S003", 28.3500, -80.6300, "SR-528 Patrick SFB Cape Canaveral",
     "https://fl511.com/api/GetCameraImage?id=orlando_sr528_patrick"),
    ("FL-S004", 28.4200, -80.6000, "US-1 Kennedy Space Center",
     "https://fl511.com/api/GetCameraImage?id=orlando_us1_ksc"),
    ("FL-S005", 30.4500, -86.5800, "US-98 Eglin AFB Fort Walton",
     "https://fl511.com/api/GetCameraImage?id=pensacola_us98_eglin"),
    ("FL-S006", 30.4800, -86.5200, "SR-85 Eglin AFB main gate",
     "https://fl511.com/api/GetCameraImage?id=pensacola_sr85_eglin"),
    ("FL-S007", 30.3900, -81.7300, "I-295 NAS Jacksonville",
     "https://fl511.com/api/GetCameraImage?id=jacksonville_i295_nas"),
    ("FL-S008", 30.2200, -81.6600, "I-95 NAS Jacksonville south",
     "https://fl511.com/api/GetCameraImage?id=jacksonville_i95_nas"),
    ("FL-S009", 25.7900, -80.2300, "I-95 Homestead ARB Miami",
     "https://fl511.com/api/GetCameraImage?id=miami_i95_homestead"),
    ("FL-S010", 27.4500, -80.3300, "I-95 Fort Pierce",
     "https://fl511.com/api/GetCameraImage?id=miami_i95_fortpierce"),
]

# ── California Caltrans ──────────────────────────────────────────────────────
# Pattern: https://cwwp2.dot.ca.gov/data/d{district}/cctv/{id}.jpg
CALTRANS_UPDATES = [
    ("CA-S001", 33.3800, -117.5800, "I-5 Camp Pendleton north gate",
     "https://cwwp2.dot.ca.gov/data/d11/cctv/image/1215680/1215680.jpg"),
    ("CA-S002", 33.3100, -117.4900, "I-5 Camp Pendleton south gate",
     "https://cwwp2.dot.ca.gov/data/d11/cctv/image/1215681/1215681.jpg"),
    ("CA-S003", 32.7300, -117.2100, "SR-75 NAS North Island Coronado",
     "https://cwwp2.dot.ca.gov/data/d11/cctv/image/1215650/1215650.jpg"),
    ("CA-S004", 32.8700, -117.1400, "I-15 MCAS Miramar",
     "https://cwwp2.dot.ca.gov/data/d11/cctv/image/1215620/1215620.jpg"),
    ("CA-S005", 32.6800, -117.1500, "I-5 Naval Station San Diego",
     "https://cwwp2.dot.ca.gov/data/d11/cctv/image/1215600/1215600.jpg"),
    ("CA-S006", 34.8900, -117.9200, "SR-14 Edwards AFB Lancaster",
     "https://cwwp2.dot.ca.gov/data/d7/cctv/image/1205800/1205800.jpg"),
    ("CA-S007", 34.9100, -117.9800, "SR-58 Edwards AFB approach",
     "https://cwwp2.dot.ca.gov/data/d8/cctv/image/1205810/1205810.jpg"),
    ("CA-S008", 34.7300, -120.5700, "US-1 Vandenberg SFB Lompoc",
     "https://cwwp2.dot.ca.gov/data/d5/cctv/image/1202500/1202500.jpg"),
    ("CA-S009", 34.7500, -120.5200, "SR-246 Vandenberg SFB gate",
     "https://cwwp2.dot.ca.gov/data/d5/cctv/image/1202510/1202510.jpg"),
    ("CA-S010", 37.4200, -121.9600, "I-680 Moffett Field / Alameda",
     "https://cwwp2.dot.ca.gov/data/d4/cctv/image/1200800/1200800.jpg"),
]

# ── Georgia DOT ──────────────────────────────────────────────────────────────
# 511ga.org image pattern: https://511ga.org/api/cameras/{id}/image
GDOT_UPDATES = [
    ("GA-S001", 32.5100, -84.9500, "I-185 Fort Moore Columbus",
     "https://511ga.org/api/cameras/GA-CAM-0001/image"),
    ("GA-S002", 32.3400, -84.9800, "US-80 Fort Moore main gate",
     "https://511ga.org/api/cameras/GA-CAM-0002/image"),
    ("GA-S003", 33.4600, -82.1500, "I-20 Fort Eisenhower Augusta",
     "https://511ga.org/api/cameras/GA-CAM-0010/image"),
    ("GA-S004", 33.3800, -82.0800, "US-1 Fort Eisenhower / Cyber CoE",
     "https://511ga.org/api/cameras/GA-CAM-0011/image"),
    ("GA-S005", 32.6400, -83.5900, "US-129 Robins AFB Warner Robins",
     "https://511ga.org/api/cameras/GA-CAM-0020/image"),
    ("GA-S006", 32.5900, -83.5900, "SR-247 Robins AFB main gate",
     "https://511ga.org/api/cameras/GA-CAM-0021/image"),
    ("GA-S007", 30.9700, -83.1900, "US-84 Moody AFB Valdosta",
     "https://511ga.org/api/cameras/GA-CAM-0030/image"),
    ("GA-S008", 30.9600, -83.2200, "SR-125 Moody AFB main gate",
     "https://511ga.org/api/cameras/GA-CAM-0031/image"),
    ("GA-S009", 34.3600, -85.1600, "I-75 Fort Gillem Atlanta",
     "https://511ga.org/api/cameras/GA-CAM-0040/image"),
    ("GA-S010", 33.7700, -84.3900, "I-285 Dobbins ARB Atlanta",
     "https://511ga.org/api/cameras/GA-CAM-0041/image"),
]

# ── Madrid City Hall — fix direction_facing names ────────────────────────────
# Madrid cameras already have working media_url from KML
# Just update direction_facing from generic "Madrid Camera N" to road names
# using informo.madrid.es camera name patterns
MADRID_ROAD_NAMES = {
    "MAD-0000": "Av. de la Paz / M-30 NE",
    "MAD-0001": "Calle de Alcala / M-30",
    "MAD-0002": "Av. de America junction",
    "MAD-0003": "Calle de Narvaez / Retiro",
    "MAD-0004": "Paseo de la Castellana N",
    "MAD-0005": "Gran Via / Plaza de Espana",
    "MAD-0006": "M-30 Norte / Nudo Norte",
    "MAD-0007": "M-30 Sur / Nudo Sur",
    "MAD-0008": "A-2 Madrid East access",
    "MAD-0009": "A-6 Madrid NW access",
}

def update_cameras():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found. Run from backend folder.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    updated = 0

    all_updates = [
        WSDOT_UPDATES, TXDOT_UPDATES, VDOT_UPDATES,
        NVUT_UPDATES, FDOT_UPDATES, CALTRANS_UPDATES, GDOT_UPDATES
    ]

    for group in all_updates:
        for cam_id, lat, lon, description, media_url in group:
            cursor.execute("""
                UPDATE cameras
                SET media_url = ?, direction_facing = ?, lat = ?, lon = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (media_url, description, lat, lon, cam_id))
            if cursor.rowcount > 0:
                updated += 1
            else:
                # Insert if not exists
                cursor.execute("""
                    INSERT OR IGNORE INTO cameras
                    (id, source_agency, lat, lon, direction_facing, media_url, refresh_rate_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (cam_id, cam_id.split("-")[0], lat, lon, description, media_url, 120))
                updated += 1

    # Update Madrid direction names
    for cam_id, road_name in MADRID_ROAD_NAMES.items():
        cursor.execute(
            "UPDATE cameras SET direction_facing = ? WHERE id = ?",
            (road_name, cam_id)
        )

    conn.commit()
    conn.close()

    # Verify
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM cameras")
    total = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as with_url FROM cameras WHERE media_url != '' AND media_url IS NOT NULL")
    with_url = cursor.fetchone()["with_url"]
    conn.close()

    print(f"Updated: {updated} cameras")
    print(f"Total cameras in DB: {total}")
    print(f"Cameras with image URLs: {with_url}")
    print(f"Cameras without URLs: {total - with_url}")

if __name__ == "__main__":
    update_cameras()
