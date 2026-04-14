"""FastAPI backend for Milano Quartieri — Neighborhood Intelligence v2."""

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from nil_store import NilStore

app = FastAPI(title="Milano Quartieri")
store = NilStore()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/nil.html")


@app.get("/api/quarters")
def get_quarters():
    return store.get_quarters()


@app.get("/api/overview")
def overview():
    return store.get_overview()


@app.get("/api/rankings")
def rankings():
    return store.get_rankings()


@app.get("/api/map-data")
def map_data(
    year_quarter: str = Query(...),
    layer: str = Query("value"),
):
    return store.get_map_data(year_quarter, layer)


@app.get("/api/nil/{nil_id}")
def nil_detail(nil_id: int):
    return store.get_nil_detail(nil_id)


@app.get("/api/opportunities")
def opportunities():
    """Commercial opportunity rankings by category."""
    return store.commercial_opportunities
