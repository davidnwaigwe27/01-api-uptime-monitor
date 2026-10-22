
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
from supabase import create_client, Client

from .checker import check_url
from .scheduler import run_forever


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client | None = None


# --------------------------------------------------
# Request models
# --------------------------------------------------

class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl


class BrowserActivityCreate(BaseModel):
    action: str = Field(min_length=1, max_length=100)
    details: dict = Field(default_factory=dict)


# --------------------------------------------------
# Application startup
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global supabase

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL or SUPABASE_KEY is missing from backend/.env "
            "or the deployment environment."
        )

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Supabase client initialized.")

    # Pass the Supabase client to the scheduler.
    run_forever(supabase, interval_seconds=60)

    yield


app = FastAPI(
    title="API Uptime Monitor",
    description="Monitor registered URLs, response times, and outages.",
    version="1.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://pulse-api-monitor.vercel.app",
        "https://api-uptime-monitor-frontend.vercel.app",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def get_db() -> Client:
    if supabase is None:
        raise HTTPException(
            status_code=503,
            detail="Database connection is not ready.",
        )
    return supabase


def normalize_url(url: str) -> str:
    return url.rstrip("/")


def format_monitor(monitor: dict) -> dict:
    """Convert a database monitor into the dashboard API format."""
    db = get_db()

    latest_response = (
        db.table("check_results")
        .select(
            "checked_at, is_success, status_code, response_time_ms"
        )
        .eq("url_id", monitor["id"])
        .order("checked_at", desc=True)
        .limit(1)
        .execute()
    )

    latest = (
        latest_response.data[0]
        if latest_response.data
        else None
    )

    if latest is None:
        current_status = "unknown"
        last_checked_at = None
        response_time_ms = None
    else:
        current_status = (
            "up" if latest["is_success"] else "down"
        )
        last_checked_at = latest["checked_at"]
        response_time_ms = latest["response_time_ms"]

    return {
        "id": monitor["id"],
        "name": monitor.get("name") or monitor["url"],
        "url": monitor["url"],
        "current_status": current_status,
        "last_checked_at": last_checked_at,
        "created_at": monitor.get("created_at"),
        "response_time_ms": response_time_ms,
    }


def find_monitor(monitor_id: int) -> dict:
    db = get_db()

    response = (
        db.table("monitored_urls")
        .select("*")
        .eq("id", monitor_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail="Monitor not found.",
        )

    return response.data[0]


# --------------------------------------------------
# Root and health
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "API Uptime Monitor API is running.",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------
# Monitors
# --------------------------------------------------

@app.get("/monitors")
def get_monitors():
    db = get_db()

    response = (
        db.table("monitored_urls")
        .select("*")
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )

    return [
        format_monitor(monitor)
        for monitor in (response.data or [])
    ]


@app.post("/monitors", status_code=status.HTTP_201_CREATED)
def create_monitor(payload: MonitorCreate):
    db = get_db()

    url = normalize_url(str(payload.url))
    name = payload.name.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Monitor name cannot be empty.",
        )

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid HTTP or HTTPS URL.",
        )

    # Check for an already registered active URL.
    existing = (
        db.table("monitored_urls")
        .select("id, url")
        .eq("is_active", True)
        .execute()
    )

    if any(
        normalize_url(item["url"]).lower() == url.lower()
        for item in (existing.data or [])
    ):
        raise HTTPException(
            status_code=409,
            detail="This URL is already registered.",
        )

    response = (
        db.table("monitored_urls")
        .insert({
            "name": name,
            "url": url,
            "is_active": True,
        })
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=500,
            detail="Could not create monitor.",
        )

    return format_monitor(response.data[0])


@app.delete("/monitors/{monitor_id}")
def delete_monitor(monitor_id: int):
    db = get_db()
    monitor = find_monitor(monitor_id)

    # Soft-delete the monitor so its history remains available.
    (
        db.table("monitored_urls")
        .update({"is_active": False})
        .eq("id", monitor["id"])
        .execute()
    )

    return {
        "message": "Monitor deleted successfully.",
        "id": monitor_id,
    }


# --------------------------------------------------
# Check history
# --------------------------------------------------

@app.get("/monitors/{monitor_id}/checks")
def get_monitor_checks(monitor_id: int):
    db = get_db()
    find_monitor(monitor_id)

    response = (
        db.table("check_results")
        .select("*")
        .eq("url_id", monitor_id)
        .order("checked_at", desc=True)
        .limit(100)
        .execute()
    )

    return response.data or []


# --------------------------------------------------
# Manual check
# --------------------------------------------------

@app.post("/monitors/{monitor_id}/check")
def manually_check_monitor(monitor_id: int):
    db = get_db()
    monitor = find_monitor(monitor_id)

    if not monitor.get("is_active", True):
        raise HTTPException(
            status_code=409,
            detail="This monitor is inactive.",
        )

    result = check_url(monitor["url"])

    checked_at = datetime.now(timezone.utc).isoformat()

    record = {
        "url_id": monitor["id"],
        "checked_at": checked_at,
        "is_success": result["is_success"],
        "status_code": result.get("status_code"),
        "response_time_ms": result.get("response_time_ms"),
        "error_type": result.get("error_type"),
        "error_message": result.get("error_message"),
    }

    saved = (
        db.table("check_results")
        .insert(record)
        .execute()
    )

    if not saved.data:
        raise HTTPException(
            status_code=500,
            detail="The check ran, but its result could not be saved.",
        )

    return {
        "monitor_id": monitor["id"],
        "url": monitor["url"],
        "current_status": (
            "up" if result["is_success"] else "down"
        ),
        **record,
    }


# --------------------------------------------------
# Browser activity
# --------------------------------------------------

@app.post("/browser-activity")
def create_browser_activity(payload: BrowserActivityCreate):
    db = get_db()

    record = {
        "action": payload.action,
        "details": payload.details,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        response = (
            db.table("browser_activity")
            .insert(record)
            .execute()
        )
    except Exception as exc:
        print(f"Could not save browser activity: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not save browser activity.",
        )

    return response.data or record


@app.get("/browser-activity")
def get_browser_activity():
    db = get_db()

    try:
        response = (
            db.table("browser_activity")
            .select("*")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
    except Exception as exc:
        print(f"Could not load browser activity: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not load browser activity.",
        )

    return response.data or []
