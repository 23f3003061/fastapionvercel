"""FastAPI endpoint for regional latency telemetry on Vercel."""

import json
import math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DATA_PATH = Path(__file__).with_name("q-vercel-latency.json")
with DATA_PATH.open(encoding="utf-8") as telemetry_file:
    TELEMETRY: list[dict[str, Any]] = json.load(telemetry_file)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/api/latency")
def latency(request: LatencyRequest) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for region in request.regions:
        records = [row for row in TELEMETRY if row["region"] == region]
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
