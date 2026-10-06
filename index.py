"""FastAPI endpoint for regional latency telemetry on Vercel."""

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# The JSON file must sit next to this file and be included in the deployment.
DATA_PATH = Path(__file__).resolve().parent / "q-vercel-latency.json"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS, PUT, DELETE, PATCH",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Max-Age": "86400",
}

app = FastAPI()


@lru_cache(maxsize=1)
def load_telemetry() -> list[dict[str, Any]]:
    """Load telemetry lazily so a missing file doesn't crash the function at import time."""
    with DATA_PATH.open(encoding="utf-8") as telemetry_file:
        return json.load(telemetry_file)


@app.middleware("http")
async def cors_headers(request: Request, call_next):
    """Add CORS headers to every response, including preflights and unhandled errors."""
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        try:
            response = await call_next(request)
        except Exception as exc:  # unhandled errors would otherwise skip the CORS headers
            print(f"Unhandled error: {exc!r}")  # visible in Vercel function logs
            response = JSONResponse({"detail": "Internal server error"}, status_code=500)
    response.headers.update(CORS_HEADERS)
    return response


class LatencyRequest(BaseModel):
    regions: list[str] = Field(min_length=1)
    threshold_ms: float


def percentile_95(values: list[float]) -> float:
    """Calculate the 95th percentile with linear interpolation."""
    ordered = sorted(values)
    position = 0.95 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


@app.get("/")
@app.get("/api/latency")
@app.get("/api/latency/")
def root():
    return {"message": "Regional Latency Telemetry API is live"}


@app.post("/api/latency")
@app.post("/api/latency/")
@app.post("/latency")
@app.post("/latency/")
def latency(request: LatencyRequest) -> dict[str, dict[str, float | int]]:
    telemetry = load_telemetry()
    result: dict[str, dict[str, float | int]] = {}
    for region in request.regions:
        records = [
            row for row in telemetry
            if row.get("region", "").lower() == region.lower()
        ]
        if not records:
            raise HTTPException(status_code=404, detail=f"No telemetry for region: {region}")
        latencies = [float(row["latency_ms"]) for row in records]
        uptimes = [float(row["uptime_pct"]) for row in records]
        result[region] = {
            "avg_latency": sum(latencies) / len(latencies),
            "p95_latency": percentile_95(latencies),
            "avg_uptime": sum(uptimes) / len(uptimes),
            "breaches": sum(value > request.threshold_ms for value in latencies),
        }
    return result