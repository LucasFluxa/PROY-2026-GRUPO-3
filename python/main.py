#!/usr/bin/env python3
"""
AquaSense - Python side (QRB2210 / Debian Linux)
Hardware: Arduino UNO Q
Comunicacion: Bridge RPC oficial (arduino.app_utils.Bridge)
Web server:   WebUI brick oficial (FastAPI + uvicorn + Socket.IO)
Puerto:       7000
"""

import json
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

try:
    from arduino.app_peripherals.camera import Camera
except Exception as exc:
    print(f"[Camera] Modulo de camara no disponible: {exc}")
    Camera = None

try:
    from arduino.app_peripherals.usb_camera import USBCamera
except Exception as exc:
    print(f"[Camera] Modulo legacy usb_camera no disponible: {exc}")
    USBCamera = None

# ── Rutas de archivos ─────────────────────────────────────────────────────────
ASSETS_DIR      = Path(__file__).parent.parent / "assets"
FISH_DATA_PATH  = ASSETS_DIR / "fish_data.json"

# ── Cargar base de datos de peces ─────────────────────────────────────────────
try:
    with open(FISH_DATA_PATH, encoding="utf-8") as fh:
        FISH_DATA = json.load(fh)
    FISH_DB = FISH_DATA.get("species", [])
    FISH_COMPAT = FISH_DATA.get("compatibility", [])
    print(f"[AquaSense] Base de datos cargada: {len(FISH_DB)} especies")
    print(f"[AquaSense] Compatibilidad entre especies cargada: {len(FISH_COMPAT)} reglas")
except FileNotFoundError:
    print(f"[AquaSense] ADVERTENCIA: No se encontro {FISH_DATA_PATH}")
    FISH_DB = []
    FISH_COMPAT = []

# ── Estado compartido ─────────────────────────────────────────────────────────
_latest = {
    "temperature": None,   # float °C, None si no hay datos aun
    "ph":          None,   # float 0-14, None si no hay datos aun
    "timestamp":   None,   # Unix timestamp de la ultima lectura
    "status":      "initializing",  # "ok" | "sensor_error" | "initializing"
}

# ── WebUI: inicializar antes de los handlers para poder llamar send_message ───
ui = WebUI(assets_dir_path=str(ASSETS_DIR))

_camera = None
_camera_initialized = False
_camera_status = {
    "available": False,
    "source": None,
    "stream": None,
    "error": "Camara no inicializada",
}

# ── Bridge RPC: funciones que el sketch STM32 puede llamar ───────────────────

def python_ready_ack() -> bool:
    """
    Handshake de arranque.
    El sketch llama esta funcion desde setup() para confirmar que Python esta listo.
    Evita que se pierdan mensajes Bridge durante el boot.
    """
    print("[Bridge] Handshake recibido: Python esta listo")
    return True


def sensor_update(temperature: float, ph: float):
    """
    Recibe temperatura y pH desde el sketch cada 2 segundos via Bridge.notify().
    Actualiza el estado global y hace push en tiempo real a los clientes WebSocket.

    Args:
        temperature: temperatura en grados Celsius (-999.0 = error de sensor)
        ph:          valor de pH en escala 0-14
    """
    _latest["temperature"] = round(temperature, 2) if temperature != -999.0 else None
    _latest["ph"]          = round(ph, 2)
    _latest["timestamp"]   = time.time()
    _latest["status"]      = "ok" if temperature != -999.0 else "sensor_error"
    snapshot = dict(_latest)

    print(f"[Bridge] sensor_update → temp={snapshot['temperature']}°C  pH={snapshot['ph']}")

    # Push inmediato a todos los clientes conectados via Socket.IO
    # El dashboard recibe esto sin necesitar hacer polling
    ui.send_message("sensor_update", snapshot)


# Registrar funciones para que el sketch pueda llamarlas
Bridge.provide("python_ready_ack", python_ready_ack)
Bridge.provide("sensor_update",    sensor_update)

# ── API endpoints ─────────────────────────────────────────────────────────────

def api_sensors():
    """
    GET /api/sensors
    Devuelve la ultima lectura de temperatura y pH.
    """
    return dict(_latest)


def api_fish():
    """
    GET /api/fish
    Devuelve la base de datos completa de especies de acuario.
    """
    return FISH_DB


def api_camera_status():
    """
    GET /api/camera/status
    Devuelve el estado de la camara USB.
    """
    if _camera is None:
        _init_camera(start=False)
    return dict(_camera_status)


def _ensure_camera_started():
    if _camera is None:
        return False

    try:
        is_started_attr = getattr(_camera, "is_started", False)
        is_started = is_started_attr() if callable(is_started_attr) else bool(is_started_attr)
        if not is_started:
            _camera.start()
            time.sleep(0.2)
        _camera_status.update({
            "available": True,
            "stream": "/api/camera/stream",
            "error": None,
        })
        return True
    except Exception as exc:
        _camera_status.update({
            "available": False,
            "stream": None,
            "error": str(exc),
        })
        print(f"[Camera] No se pudo iniciar la camara: {exc}")
        return False


def api_camera_stream():
    """
    GET /api/camera/stream
    Stream MJPEG de la camara USB.
    """
    if _camera is None:
        _init_camera(start=True)

    if not _ensure_camera_started():
        return JSONResponse({"error": _camera_status["error"]}, status_code=503)

    from arduino.app_utils.image import compress_to_jpeg

    def generate_frames():
        while True:
            try:
                if not _ensure_camera_started():
                    time.sleep(0.5)
                    continue

                frame = _camera.capture()
                if frame is None:
                    time.sleep(0.03)
                    continue

                jpeg = compress_to_jpeg(frame, quality=78)
                if jpeg is None:
                    time.sleep(0.03)
                    continue

                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            except Exception as exc:
                _camera_status.update({
                    "available": False,
                    "stream": None,
                    "error": str(exc),
                })
                print(f"[Camera] Stream detenido: {exc}")
                break

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


def _parse_ids(ids_param: str):
    return {int(x) for x in ids_param.split(",") if x.strip()}


def _species_issues_by_id(requested_ids):
    selected = set(requested_ids)
    issues_by_id = {fish_id: [] for fish_id in selected}
    fish_by_id = {int(fish["id"]): fish for fish in FISH_DB}

    for pair in FISH_COMPAT:
        if pair.get("compatible", True):
            continue

        id1 = int(pair.get("fish_1_id"))
        id2 = int(pair.get("fish_2_id"))
        if id1 not in selected or id2 not in selected:
            continue

        fish1 = fish_by_id.get(id1)
        fish2 = fish_by_id.get(id2)
        reason = pair.get("reason") or "Incompatibilidad entre especies"

        issues_by_id[id1].append({
            "type": "species",
            "other_id": id2,
            "other_name": (fish2 or {}).get("common_name") or pair.get("fish_2_name") or str(id2),
            "message": reason,
        })
        issues_by_id[id2].append({
            "type": "species",
            "other_id": id1,
            "other_name": (fish1 or {}).get("common_name") or pair.get("fish_1_name") or str(id1),
            "message": reason,
        })

    return issues_by_id


async def api_fish_pairs_compatibility(request: Request):
    """
    GET /api/fish-pairs-compatibility?ids=1,5,12
    Devuelve compatibilidad directa entre cada par de especies indicado.
    """
    ids_param = request.query_params.get("ids", "")

    try:
        fish_ids = list(_parse_ids(ids_param))
    except ValueError:
        return JSONResponse({"error": "IDs de peces invalidos"}, status_code=400)

    if len(fish_ids) < 2:
        return {"compatibilities": []}

    result = []
    for i, id1 in enumerate(fish_ids):
        for id2 in fish_ids[i + 1:]:
            compat = None
            for pair in FISH_COMPAT:
                pair_id1 = pair.get("fish_1_id")
                pair_id2 = pair.get("fish_2_id")
                if (pair_id1 == id1 and pair_id2 == id2) or (pair_id1 == id2 and pair_id2 == id1):
                    compat = pair
                    break

            result.append({
                "fish_1_id": id1,
                "fish_2_id": id2,
                "compatible": compat.get("compatible", True) if compat else True,
                "reason": compat.get("reason", "Sin informacion") if compat else "Sin informacion",
            })

    return {"compatibilities": result}


async def api_compatibility(request: Request):
    """
    GET /api/compatibility?ids=1,5,12
    Verifica si los peces indicados son compatibles con los parametros actuales del agua.
    Devuelve lista de issues por especie (temperatura fuera de rango, pH fuera de rango).
    """
    ids_param = request.query_params.get("ids", "")

    # Parsear IDs
    try:
        requested_ids = _parse_ids(ids_param)
    except ValueError:
        return JSONResponse(
            {"error": "Parametro 'ids' invalido. Usa numeros separados por coma, ej: ?ids=1,5,12"},
            status_code=400
        )

    if not requested_ids:
        return JSONResponse({"error": "No se indicaron IDs de peces"}, status_code=400)

    # Obtener lecturas actuales
    temp = _latest["temperature"]
    ph   = _latest["ph"]

    if temp is None or ph is None:
        return JSONResponse(
            {"error": "Datos de sensor no disponibles aun. Espera a que el sketch arranque."},
            status_code=503
        )

    # Verificar compatibilidad para cada pez solicitado
    results = []
    species_issues = _species_issues_by_id(requested_ids)
    for fish in FISH_DB:
        if fish["id"] not in requested_ids:
            continue

        issues = list(species_issues.get(fish["id"], []))

        # Verificar temperatura
        if not (fish["temp_min"] <= temp <= fish["temp_max"]):
            issues.append({
                "type":      "temperature",
                "direction": "low" if temp < fish["temp_min"] else "high",
                "current":   temp,
                "ideal_min": fish["temp_min"],
                "ideal_max": fish["temp_max"],
            })

        # Verificar pH
        if not (fish["ph_min"] <= ph <= fish["ph_max"]):
            issues.append({
                "type":      "ph",
                "direction": "low" if ph < fish["ph_min"] else "high",
                "current":   ph,
                "ideal_min": fish["ph_min"],
                "ideal_max": fish["ph_max"],
            })

        results.append({
            "id":         fish["id"],
            "name":       fish["common_name"],
            "scientific": fish["scientific_name"],
            "compatible": len(issues) == 0,
            "issues":     issues,
        })

    return {
        "temperature": temp,
        "ph":          ph,
        "fish":        results,
    }


# Registrar endpoints en el brick WebUI (FastAPI internamente)
ui.expose_api("GET", "/api/sensors",       api_sensors)
ui.expose_api("GET", "/api/fish",          api_fish)
ui.expose_api("GET", "/api/camera/status", api_camera_status)
ui.expose_api("GET", "/api/camera/stream", api_camera_stream)
ui.expose_api("GET", "/api/fish-pairs-compatibility", api_fish_pairs_compatibility)
ui.expose_api("GET", "/api/compatibility", api_compatibility)


def _init_camera(start: bool = False):
    global _camera, _camera_initialized

    if _camera is not None or _camera_initialized:
        return

    _camera_initialized = True

    if Camera is None and USBCamera is None:
        _camera_status.update({
            "available": False,
            "source": None,
            "stream": None,
            "error": "No hay modulo de camara disponible en App Lab",
        })
        return

    candidates = []
    if Camera is not None:
        candidates.extend([
            ("usb:0", lambda: Camera("usb:0", resolution=(640, 480), fps=15)),
            ("/dev/video0", lambda: Camera("/dev/video0", resolution=(640, 480), fps=15)),
            ("/dev/video1", lambda: Camera("/dev/video1", resolution=(640, 480), fps=15)),
        ])
    if USBCamera is not None:
        candidates.append(("USBCamera", lambda: USBCamera(resolution=(640, 480), fps=15)))

    for source, make_camera in candidates:
        try:
            camera = make_camera()
            _camera = camera
            if start:
                _ensure_camera_started()
            _camera_status.update({
                "available": True,
                "source": source,
                "stream": "/api/camera/stream",
                "error": None,
            })
            print(f"[Camera] Camara USB lista en {source}")
            return
        except Exception as exc:
            _camera_status.update({
                "available": False,
                "source": source,
                "stream": None,
                "error": str(exc),
            })
            print(f"[Camera] No se pudo abrir {source}: {exc}")

# ── Arranque ──────────────────────────────────────────────────────────────────
print(f"[AquaSense] Dashboard disponible en {ui.url}")
print("[AquaSense] Esperando datos del sketch via Bridge...")

# App.run() inicia el brick WebUI + mantiene el Bridge vivo
App.run()
