	#!/usr/bin/env python3
"""
AquaSense - Python side (QRB2210 / Debian Linux)
Hardware: Arduino UNO Q
Comunicacion: Bridge RPC oficial (arduino.app_bricks.bridge)
Web server:   WebUI brick oficial (FastAPI + uvicorn + Socket.IO)
Puerto:       7000
"""

import json
import threading
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI
from arduino.app_bricks.bridge import Bridge

# ── Rutas de archivos ─────────────────────────────────────────────────────────
ASSETS_DIR   = Path(__file__).parent.parent / "assets"
FISH_DB_PATH = ASSETS_DIR / "fish_database.json"

# ── Cargar base de datos de peces ─────────────────────────────────────────────
try:
    with open(FISH_DB_PATH, encoding="utf-8") as fh:
        FISH_DB = json.load(fh)
    print(f"[AquaSense] Base de datos cargada: {len(FISH_DB)} especies")
except FileNotFoundError:
    print(f"[AquaSense] ADVERTENCIA: No se encontro {FISH_DB_PATH}")
    FISH_DB = []

# ── Estado compartido (protegido con lock para thread safety) ─────────────────
_lock = threading.Lock()
_latest = {
    "temperature": None,   # float °C, None si no hay datos aun
    "ph":          None,   # float 0-14, None si no hay datos aun
    "timestamp":   None,   # Unix timestamp de la ultima lectura
    "status":      "initializing",  # "ok" | "sensor_error" | "initializing"
}

# ── WebUI: inicializar antes de los handlers para poder llamar send_message ───
ui = WebUI(assets_dir_path=str(ASSETS_DIR))

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
    with _lock:
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

# ── Fallback: polling Bridge cada 5 s ─────────────────────────────────────────
# Por si algun Bridge.notify() se pierde, consultamos directamente al sketch
def _poll_bridge():
    while True:
        time.sleep(5)
        try:
            temp = 0.0
            ph   = 0.0
            Bridge.call("get_temperature").result(temp)
            Bridge.call("get_ph").result(ph)

            with _lock:
                age = time.time() - (_latest["timestamp"] or 0)
                # Solo actualizar si el notify lleva mas de 4 s sin llegar
                if age > 4:
                    _latest["temperature"] = round(temp, 2) if temp != -999.0 else None
                    _latest["ph"]          = round(ph, 2)
                    _latest["timestamp"]   = time.time()
                    _latest["status"]      = "ok" if temp != -999.0 else "sensor_error"
                    print(f"[Poll] Fallback update → temp={_latest['temperature']}°C  pH={_latest['ph']}")

        except Exception as exc:
            print(f"[Poll] Error al consultar Bridge: {exc}")


threading.Thread(target=_poll_bridge, daemon=True, name="bridge-poll").start()

# ── API endpoints ─────────────────────────────────────────────────────────────

def api_sensors():
    """
    GET /api/sensors
    Devuelve la ultima lectura de temperatura y pH.
    """
    with _lock:
        return dict(_latest)


def api_fish():
    """
    GET /api/fish
    Devuelve la base de datos completa de especies de acuario.
    """
    return FISH_DB


async def api_compatibility(request: Request):
    """
    GET /api/compatibility?ids=1,5,12
    Verifica si los peces indicados son compatibles con los parametros actuales del agua.
    Devuelve lista de issues por especie (temperatura fuera de rango, pH fuera de rango).
    """
    ids_param = request.query_params.get("ids", "")

    # Parsear IDs
    try:
        requested_ids = {int(x) for x in ids_param.split(",") if x.strip()}
    except ValueError:
        return JSONResponse(
            {"error": "Parametro 'ids' invalido. Usa numeros separados por coma, ej: ?ids=1,5,12"},
            status_code=400
        )

    if not requested_ids:
        return JSONResponse({"error": "No se indicaron IDs de peces"}, status_code=400)

    # Obtener lecturas actuales
    with _lock:
        temp = _latest["temperature"]
        ph   = _latest["ph"]

    if temp is None or ph is None:
        return JSONResponse(
            {"error": "Datos de sensor no disponibles aun. Espera a que el sketch arranque."},
            status_code=503
        )

    # Verificar compatibilidad para cada pez solicitado
    results = []
    for fish in FISH_DB:
        if fish["id"] not in requested_ids:
            continue

        issues = []

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
ui.expose_api("GET", "/api/compatibility", api_compatibility)

# ── Arranque ──────────────────────────────────────────────────────────────────
print(f"[AquaSense] Dashboard disponible en {ui.url}")
print("[AquaSense] Esperando datos del sketch via Bridge...")

# App.run() inicia el brick WebUI + mantiene el Bridge vivo
App.run()
