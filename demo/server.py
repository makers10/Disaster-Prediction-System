"""
Disaster Prediction System — Local Demo Server
===============================================
Runs entirely in-memory. No database, no Kafka, no external services needed.
Just: python demo/server.py

Open http://localhost:8000 in your browser.
"""

from __future__ import annotations

import json
import os as _os
_DEMO_DIR = _os.path.dirname(_os.path.abspath(__file__))
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# In-memory demo data store
# ---------------------------------------------------------------------------

DISASTER_TYPES = ["flood", "heatwave", "drought", "landslide", "cyclone"]
FORECAST_HORIZONS = [6, 24, 72]
RISK_LEVELS = ["Low", "Medium", "High"]

DEMO_REGIONS = [
    {"region_id": "mumbai",    "name": "Mumbai",    "lat": 19.07, "lon": 72.87},
    {"region_id": "delhi",     "name": "Delhi",     "lat": 28.61, "lon": 77.20},
    {"region_id": "chennai",   "name": "Chennai",   "lat": 13.08, "lon": 80.27},
    {"region_id": "kolkata",   "name": "Kolkata",   "lat": 22.57, "lon": 88.36},
    {"region_id": "bangalore", "name": "Bangalore", "lat": 12.97, "lon": 77.59},
    {"region_id": "hyderabad", "name": "Hyderabad", "lat": 17.38, "lon": 78.48},
    {"region_id": "pune",      "name": "Pune",      "lat": 18.52, "lon": 73.85},
    {"region_id": "ahmedabad", "name": "Ahmedabad", "lat": 23.02, "lon": 72.57},
]

# District-level data: city → list of districts with GPS coords
DISTRICTS: Dict[str, List[Dict[str, Any]]] = {
    "mumbai": [
        {"district_id": "mumbai-south",    "name": "Mumbai South",    "lat": 18.93, "lon": 72.83},
        {"district_id": "mumbai-suburban", "name": "Mumbai Suburban", "lat": 19.10, "lon": 72.87},
        {"district_id": "thane",           "name": "Thane",           "lat": 19.22, "lon": 72.98},
        {"district_id": "raigad",          "name": "Raigad",          "lat": 18.52, "lon": 73.18},
        {"district_id": "palghar",         "name": "Palghar",         "lat": 19.70, "lon": 72.77},
    ],
    "delhi": [
        {"district_id": "central-delhi",   "name": "Central Delhi",   "lat": 28.65, "lon": 77.22},
        {"district_id": "north-delhi",     "name": "North Delhi",     "lat": 28.73, "lon": 77.20},
        {"district_id": "south-delhi",     "name": "South Delhi",     "lat": 28.52, "lon": 77.22},
        {"district_id": "east-delhi",      "name": "East Delhi",      "lat": 28.65, "lon": 77.30},
        {"district_id": "west-delhi",      "name": "West Delhi",      "lat": 28.65, "lon": 77.10},
        {"district_id": "new-delhi",       "name": "New Delhi",       "lat": 28.61, "lon": 77.21},
    ],
    "chennai": [
        {"district_id": "chennai-north",   "name": "Chennai North",   "lat": 13.15, "lon": 80.28},
        {"district_id": "chennai-south",   "name": "Chennai South",   "lat": 12.98, "lon": 80.22},
        {"district_id": "kancheepuram",    "name": "Kancheepuram",    "lat": 12.83, "lon": 79.70},
        {"district_id": "tiruvallur",      "name": "Tiruvallur",      "lat": 13.14, "lon": 79.91},
        {"district_id": "chengalpattu",    "name": "Chengalpattu",    "lat": 12.69, "lon": 79.98},
    ],
    "kolkata": [
        {"district_id": "kolkata-north",   "name": "Kolkata North",   "lat": 22.62, "lon": 88.37},
        {"district_id": "kolkata-south",   "name": "Kolkata South",   "lat": 22.50, "lon": 88.35},
        {"district_id": "howrah",          "name": "Howrah",          "lat": 22.59, "lon": 88.31},
        {"district_id": "north-24-parganas","name": "North 24 Parganas","lat": 22.73, "lon": 88.40},
        {"district_id": "south-24-parganas","name": "South 24 Parganas","lat": 22.15, "lon": 88.43},
    ],
    "bangalore": [
        {"district_id": "bangalore-urban", "name": "Bangalore Urban", "lat": 12.97, "lon": 77.59},
        {"district_id": "bangalore-rural", "name": "Bangalore Rural", "lat": 13.22, "lon": 77.50},
        {"district_id": "ramanagara",      "name": "Ramanagara",      "lat": 12.72, "lon": 77.28},
        {"district_id": "chikkaballapur",  "name": "Chikkaballapur",  "lat": 13.43, "lon": 77.73},
        {"district_id": "tumkur",          "name": "Tumkur",          "lat": 13.34, "lon": 77.10},
    ],
    "hyderabad": [
        {"district_id": "hyderabad-dist",  "name": "Hyderabad",       "lat": 17.38, "lon": 78.48},
        {"district_id": "rangareddy",      "name": "Rangareddy",      "lat": 17.25, "lon": 78.40},
        {"district_id": "medchal",         "name": "Medchal-Malkajgiri","lat": 17.55, "lon": 78.55},
        {"district_id": "sangareddy",      "name": "Sangareddy",      "lat": 17.62, "lon": 78.08},
        {"district_id": "vikarabad",       "name": "Vikarabad",       "lat": 17.33, "lon": 77.90},
    ],
    "pune": [
        {"district_id": "pune-city",       "name": "Pune City",       "lat": 18.52, "lon": 73.85},
        {"district_id": "pimpri-chinchwad","name": "Pimpri-Chinchwad","lat": 18.63, "lon": 73.80},
        {"district_id": "maval",           "name": "Maval",           "lat": 18.72, "lon": 73.55},
        {"district_id": "haveli",          "name": "Haveli",          "lat": 18.45, "lon": 73.95},
        {"district_id": "baramati",        "name": "Baramati",        "lat": 18.15, "lon": 74.58},
    ],
    "ahmedabad": [
        {"district_id": "ahmedabad-city",  "name": "Ahmedabad City",  "lat": 23.02, "lon": 72.57},
        {"district_id": "gandhinagar",     "name": "Gandhinagar",     "lat": 23.22, "lon": 72.65},
        {"district_id": "anand",           "name": "Anand",           "lat": 22.55, "lon": 72.95},
        {"district_id": "kheda",           "name": "Kheda",           "lat": 22.75, "lon": 72.68},
        {"district_id": "mehsana",         "name": "Mehsana",         "lat": 23.60, "lon": 72.38},
    ],
}

# Shared in-memory state
_state: Dict[str, Any] = {
    "predictions": {},          # region_id → list of PredictionRecord
    "district_predictions": {}, # district_id → list of PredictionRecord
    "alerts": [],
    "crowd_reports": [],
    "chat_history": [],
    "sensor_readings": {},      # region_id → latest SensorReading
    "district_sensors": {},     # district_id → latest SensorReading
}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Demo data generators
# ---------------------------------------------------------------------------

def _make_prediction(region_id: str, disaster_type: str, horizon: int) -> Dict[str, Any]:
    """Generate a realistic-looking prediction for demo purposes."""
    rng = random.Random(f"{region_id}{disaster_type}{horizon}{int(time.time() // 3600)}")

    # Make floods more likely in coastal cities, heatwaves in inland cities
    coastal = region_id in ("mumbai", "chennai", "kolkata")
    if disaster_type == "flood" and coastal:
        prob = rng.uniform(40, 85)
    elif disaster_type == "heatwave" and not coastal:
        prob = rng.uniform(35, 75)
    elif disaster_type == "drought":
        prob = rng.uniform(10, 50)
    else:
        prob = rng.uniform(5, 65)

    # Longer horizons = slightly lower probability
    discount = {6: 1.0, 24: 0.92, 72: 0.82}[horizon]
    prob = min(100.0, prob * discount)

    if prob >= 65:
        risk_level = "High"
    elif prob >= 35:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    tti = None
    if risk_level in ("Medium", "High"):
        tti = round(rng.uniform(horizon * 0.2, horizon * 0.8), 1)

    severity = round(prob * 0.9 * discount, 1)

    return {
        "prediction_id": str(uuid.uuid4()),
        "region_id": region_id,
        "disaster_type": disaster_type,
        "forecast_horizon_h": horizon,
        "risk_level": risk_level,
        "probability_pct": round(prob, 1),
        "time_to_impact_h": tti,
        "severity_index": round(severity, 1),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": "demo-1.0",
    }


def _make_sensor_reading(region_id: str) -> Dict[str, Any]:
    rng = random.Random(f"{region_id}{int(time.time() // 900)}")
    coastal = region_id in ("mumbai", "chennai", "kolkata")
    return {
        "sensor_id": f"sensor-{region_id}-001",
        "region_id": region_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rainfall_mm": round(rng.uniform(0, 80 if coastal else 20), 1),
        "temperature_c": round(rng.uniform(22, 42), 1),
        "river_level_m": round(rng.uniform(0.5, 4.5 if coastal else 2.0), 2),
        "soil_moisture_pct": round(rng.uniform(20, 85), 1),
        "wind_speed_kmh": round(rng.uniform(5, 60), 1),
        "wind_direction_deg": round(rng.uniform(0, 360), 0),
        "is_anomalous": False,
        "stream_status": "ok",
    }


def _get_xai_explanation(region_id: str, disaster_type: str, risk_level: str) -> Dict[str, Any]:
    """Generate a demo XAI explanation."""
    factors_map = {
        "flood": [
            ("heavy rainfall", 42), ("rising river levels", 28),
            ("high soil moisture", 18), ("low elevation terrain", 12),
        ],
        "heatwave": [
            ("high temperature", 50), ("low humidity", 25),
            ("strong winds", 15), ("historical heatwave pattern", 10),
        ],
        "drought": [
            ("rainfall deficit", 40), ("declining soil moisture", 30),
            ("temperature anomaly", 20), ("extended dry period", 10),
        ],
        "landslide": [
            ("intense rainfall", 35), ("steep terrain slope", 25),
            ("high soil moisture", 25), ("elevation gradient", 15),
        ],
        "cyclone": [
            ("strong winds", 40), ("dense cloud cover", 25),
            ("warm sea surface", 20), ("wind direction", 15),
        ],
    }
    factors = factors_map.get(disaster_type, [("unknown factor", 100)])
    top = factors[:3]
    summary_parts = [f"{name} ({pct}%)" for name, pct in top]
    summary = f"{disaster_type.capitalize()} risk is {risk_level} due to: {', '.join(summary_parts)}."
    return {
        "contributing_factors": [
            {"feature_name": name.replace(" ", "_"), "contribution_pct": pct, "direction": "positive"}
            for name, pct in factors
        ],
        "plain_language_summary": summary,
    }


def _refresh_predictions() -> None:
    """Regenerate all predictions (called every 60s in background)."""
    with _lock:
        for region in DEMO_REGIONS:
            rid = region["region_id"]
            _state["predictions"][rid] = []
            for dtype in DISASTER_TYPES:
                for horizon in FORECAST_HORIZONS:
                    _state["predictions"][rid].append(_make_prediction(rid, dtype, horizon))
            _state["sensor_readings"][rid] = _make_sensor_reading(rid)

        # District-level predictions
        for region_id, districts in DISTRICTS.items():
            for district in districts:
                did = district["district_id"]
                _state["district_predictions"][did] = []
                for dtype in DISASTER_TYPES:
                    for horizon in FORECAST_HORIZONS:
                        _state["district_predictions"][did].append(
                            _make_prediction(did, dtype, horizon)
                        )
                _state["district_sensors"][did] = _make_sensor_reading(did)


def _background_refresh() -> None:
    while True:
        _refresh_predictions()
        time.sleep(60)


# ---------------------------------------------------------------------------
# Chat / Conversational AI
# ---------------------------------------------------------------------------

def _chat_response(query: str, region_id: str | None) -> Dict[str, Any]:
    q = query.lower()

    # Determine region from query if not provided
    if not region_id:
        for r in DEMO_REGIONS:
            if r["name"].lower() in q or r["region_id"] in q:
                region_id = r["region_id"]
                break

    if not region_id:
        return {
            "response": "I couldn't determine your location. Please specify a city (e.g., 'What is the flood risk in Mumbai?')",
            "intent": "location_clarification",
            "region_id": None,
        }

    with _lock:
        preds = _state["predictions"].get(region_id, [])

    if not preds:
        return {"response": f"No prediction data available for {region_id}.", "intent": "risk_query", "region_id": region_id}

    # Find highest risk prediction
    risk_order = {"High": 3, "Medium": 2, "Low": 1}
    top = max(preds, key=lambda p: (risk_order[p["risk_level"]], p["probability_pct"]))

    # Determine intent
    if any(w in q for w in ["safe", "travel", "go to", "visit"]):
        intent = "safety_recommendation"
        if top["risk_level"] == "High":
            response = f"It is NOT safe to travel to {region_id.capitalize()}. There is a {top['disaster_type']} High risk alert ({top['probability_pct']}% probability). Avoid travel and follow official guidance."
        elif top["risk_level"] == "Medium":
            response = f"Exercise caution. There is a {top['disaster_type']} Medium risk ({top['probability_pct']}%) in {region_id.capitalize()}. Monitor official channels before travelling."
        else:
            response = f"Current risk levels in {region_id.capitalize()} are Low. Travel appears safe, but always check official advisories."

    elif any(w in q for w in ["precaution", "prepare", "what should", "what to do", "how to"]):
        intent = "precautionary_actions"
        actions = {
            "flood": "Move to higher ground, avoid flood-prone areas, prepare emergency supplies, follow evacuation orders.",
            "heatwave": "Stay indoors during peak hours (12–4pm), drink plenty of water, check on vulnerable neighbours.",
            "drought": "Conserve water, avoid open burning, monitor water supply levels.",
            "landslide": "Avoid steep slopes, monitor for unusual sounds or ground movement, be ready to evacuate.",
            "cyclone": "Secure loose objects, stay indoors, follow evacuation orders if issued.",
        }
        response = f"{top['disaster_type'].capitalize()} precautions for {region_id.capitalize()}: {actions.get(top['disaster_type'], 'Stay alert and follow official guidance.')}"

    else:
        intent = "risk_query"
        # Filter by disaster type if mentioned
        dtype_filter = next((d for d in DISASTER_TYPES if d in q), None)
        relevant = [p for p in preds if p["disaster_type"] == dtype_filter] if dtype_filter else preds
        relevant_6h = [p for p in relevant if p["forecast_horizon_h"] == 6]

        lines = []
        for p in sorted(relevant_6h, key=lambda x: -risk_order[x["risk_level"]])[:3]:
            tti = f" (impact in ~{p['time_to_impact_h']}h)" if p["time_to_impact_h"] else ""
            lines.append(f"{p['disaster_type']}: {p['risk_level']} ({p['probability_pct']}%){tti}")

        response = f"Current risk for {region_id.capitalize()} (6h forecast): " + " | ".join(lines)

    return {"response": response, "intent": intent, "region_id": region_id, "top_prediction": top}


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

def _json(data: Any) -> bytes:
    return json.dumps(data, default=str).encode()


class DemoHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def _send(self, status: int, data: Any, content_type: str = "application/json") -> None:
        body = data if isinstance(data, bytes) else _json(data)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # Serve dashboard UI
        if path in ("", "/"):
            self._serve_file("demo/index.html", "text/html")
            return

        # API routes
        if path == "/api/regions":
            dtype = (qs.get("disaster_type") or [None])[0]
            with _lock:
                result = []
                for region in DEMO_REGIONS:
                    rid = region["region_id"]
                    preds = _state["predictions"].get(rid, [])
                    if dtype:
                        preds = [p for p in preds if p["disaster_type"] == dtype]
                    if not preds:
                        continue
                    risk_order = {"High": 3, "Medium": 2, "Low": 1}
                    top = max(preds, key=lambda p: risk_order[p["risk_level"]])
                    color = {"High": "Red", "Medium": "Yellow", "Low": "Green"}[top["risk_level"]]
                    result.append({
                        "region_id": rid,
                        "name": region["name"],
                        "lat": region["lat"],
                        "lon": region["lon"],
                        "risk_level": top["risk_level"],
                        "color": color,
                        "last_prediction_at": top["generated_at"],
                    })
            self._send(200, result)
            return

        if path.startswith("/api/regions/"):
            rid = path.split("/api/regions/")[1]
            with _lock:
                preds = _state["predictions"].get(rid, [])
            if not preds:
                self._send(404, {"error": "Region not found"})
                return
            # Latest per disaster type (6h horizon)
            by_type = {}
            for p in preds:
                if p["forecast_horizon_h"] == 6:
                    by_type[p["disaster_type"]] = p
            region_info = next((r for r in DEMO_REGIONS if r["region_id"] == rid), {"region_id": rid, "name": rid})
            self._send(200, {
                "region_id": rid,
                "name": region_info.get("name", rid),
                "disaster_types": list(by_type.values()),
            })
            return

        if path == "/api/predictions":
            rid = (qs.get("region_id") or [None])[0]
            dtype = (qs.get("disaster_type") or [None])[0]
            with _lock:
                all_preds = []
                for r_id, preds in _state["predictions"].items():
                    if rid and r_id != rid:
                        continue
                    for p in preds:
                        if dtype and p["disaster_type"] != dtype:
                            continue
                        all_preds.append(p)
            self._send(200, all_preds[:200])
            return

        if path == "/api/sensors":
            rid = (qs.get("region_id") or [None])[0]
            with _lock:
                if rid:
                    data = _state["sensor_readings"].get(rid, {})
                else:
                    data = list(_state["sensor_readings"].values())
            self._send(200, data)
            return

        if path == "/api/xai":
            rid = (qs.get("region_id") or [None])[0]
            dtype = (qs.get("disaster_type") or ["flood"])[0]
            with _lock:
                preds = _state["predictions"].get(rid, [])
            p = next((x for x in preds if x["disaster_type"] == dtype and x["forecast_horizon_h"] == 6), None)
            if not p:
                self._send(404, {"error": "No prediction found"})
                return
            xai = _get_xai_explanation(rid, dtype, p["risk_level"])
            self._send(200, {**p, **xai})
            return

        if path == "/api/crowd-reports":
            with _lock:
                self._send(200, _state["crowd_reports"])
            return

        if path == "/api/alerts":
            with _lock:
                self._send(200, _state["alerts"][-50:])
            return

        if path == "/api/history/events":
            # Return synthetic historical events
            events = []
            for region in DEMO_REGIONS:
                for dtype in ["flood", "heatwave"]:
                    events.append({
                        "event_id": str(uuid.uuid4()),
                        "region_id": region["region_id"],
                        "disaster_type": dtype,
                        "start_date": "2024-07-15",
                        "end_date": "2024-07-18",
                        "severity": round(random.uniform(40, 90), 1),
                        "source": "demo-historical-data",
                    })
            self._send(200, events)
            return

        if path == "/api/history/accuracy":
            accuracy = []
            for dtype in DISASTER_TYPES:
                accuracy.append({
                    "disaster_type": dtype,
                    "precision": round(random.uniform(0.72, 0.91), 3),
                    "recall": round(random.uniform(0.68, 0.88), 3),
                    "false_alarm_rate": round(random.uniform(0.05, 0.18), 3),
                    "total_predictions": random.randint(120, 500),
                    "from": "2024-01-01T00:00:00+00:00",
                    "to": datetime.now(timezone.utc).isoformat(),
                })
            self._send(200, accuracy)
            return

        # ── District endpoints ──────────────────────────────────────────
        if path == "/api/districts":
            # Returns all districts, optionally filtered by region_id
            region_filter = (qs.get("region_id") or [None])[0]
            dtype = (qs.get("disaster_type") or [None])[0]
            result = []
            for region_id, districts in DISTRICTS.items():
                if region_filter and region_id != region_filter:
                    continue
                for d in districts:
                    did = d["district_id"]
                    with _lock:
                        preds = _state["district_predictions"].get(did, [])
                    if dtype:
                        preds = [p for p in preds if p["disaster_type"] == dtype]
                    if not preds:
                        continue
                    risk_order = {"High": 3, "Medium": 2, "Low": 1}
                    top = max(preds, key=lambda p: risk_order[p["risk_level"]])
                    color = {"High": "Red", "Medium": "Yellow", "Low": "Green"}[top["risk_level"]]
                    result.append({
                        "district_id": did,
                        "name": d["name"],
                        "region_id": region_id,
                        "lat": d["lat"],
                        "lon": d["lon"],
                        "risk_level": top["risk_level"],
                        "color": color,
                        "last_prediction_at": top["generated_at"],
                    })
            self._send(200, result)
            return

        if path.startswith("/api/districts/"):
            did = path.split("/api/districts/")[1]
            with _lock:
                preds = _state["district_predictions"].get(did, [])
                sensor = _state["district_sensors"].get(did, {})
            if not preds:
                self._send(404, {"error": "District not found"})
                return
            by_type = {}
            for p in preds:
                if p["forecast_horizon_h"] == 6:
                    by_type[p["disaster_type"]] = p
            # Find district info
            dist_info = None
            for region_id, districts in DISTRICTS.items():
                for d in districts:
                    if d["district_id"] == did:
                        dist_info = {**d, "region_id": region_id}
                        break
            self._send(200, {
                "district_id": did,
                "name": dist_info["name"] if dist_info else did,
                "region_id": dist_info["region_id"] if dist_info else "",
                "lat": dist_info["lat"] if dist_info else 0,
                "lon": dist_info["lon"] if dist_info else 0,
                "disaster_types": list(by_type.values()),
                "sensor": sensor,
            })
            return

        self._send(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/api/chat":
            query = body.get("query", "")
            region_id = body.get("region_id")
            result = _chat_response(query, region_id)
            with _lock:
                _state["chat_history"].append({"query": query, "response": result["response"]})
            self._send(200, result)
            return

        if path == "/api/crowd-reports":
            report = {
                "report_id": str(uuid.uuid4()),
                "user_id": body.get("user_id", "demo-user"),
                "region_id": body.get("region_id", "mumbai"),
                "disaster_type": body.get("disaster_type", "flood"),
                "image_url": "demo://no-image",
                "description": body.get("description", ""),
                "reported_at": datetime.now(timezone.utc).isoformat(),
                "location": {"lat": body.get("lat", 19.07), "lon": body.get("lon", 72.87)},
                "validation_status": "pending",
            }
            with _lock:
                _state["crowd_reports"].append(report)
            self._send(201, report)
            return

        self._send(404, {"error": "Not found"})

    def _serve_file(self, filepath: str, content_type: str) -> None:
        # Resolve relative to the demo directory
        abs_path = _os.path.join(_DEMO_DIR, _os.path.basename(filepath))
        try:
            with open(abs_path, "rb") as f:
                content = f.read()
            self._send(200, content, content_type)
        except FileNotFoundError:
            self._send(404, b"File not found", "text/plain")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Disaster Prediction System — Local Demo")
    print("=" * 60)
    print("  Generating demo data...")
    _refresh_predictions()
    print(f"  Loaded {len(DEMO_REGIONS)} regions with predictions")
    print()
    print("  Starting server at http://localhost:8000")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    # Background refresh thread
    t = threading.Thread(target=_background_refresh, daemon=True)
    t.start()

    server = HTTPServer(("0.0.0.0", 8000), DemoHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDemo server stopped.")
