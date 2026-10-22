
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

from .checker import check_url
from .scheduler import run_forever


# --------------------------------------------------
# 1. Environment and Supabase configuration
# --------------------------------------------------

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client | None = None


def get_db() -> Client:
    """Return the initialized Supabase client."""
    if supabase is None:
        raise HTTPException(
            status_code=503,
            detail="Database connection is not initialized.",
        )

    return supabase


# --------------------------------------------------
# 2. Start FastAPI and the background scheduler
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global supabase

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL or SUPABASE_KEY is missing from backend/.env"
        )

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("Supabase client initialized.")

    run_forever(supabase, interval_seconds=60)

    yield


app = FastAPI(
    title="API Uptime Monitor",
    description="Monitor website availability and browser activity.",
    version="1.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------
# 3. CORS configuration
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5501",
        "http://127.0.0.1:5501",
    ],
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# 4. Request models
# --------------------------------------------------

class MonitorCreate(BaseModel):
    name: str
    url: str


class BrowserDomain(BaseModel):
    domain: str
    tab_count: int


class BrowserActivityUpdate(BaseModel):
    domains: list[BrowserDomain]


# --------------------------------------------------
# 5. Helpers for website monitors
# --------------------------------------------------

def monitor_status(monitor_id: int) -> dict:
    """Get the latest saved check, including error details."""

    response = (
        get_db()
        .table("check_results")
        .select("*")
        .eq("url_id", monitor_id)
        .order("checked_at", desc=True)
        .limit(1)
        .execute()
    )

    records = response.data or []

    if not records:
        return {
            "current_status": "unknown",
            "last_checked_at": None,
            "response_time_ms": None,
            "status_code": None,
            "error_type": None,
            "error_message": None,
        }

    latest = records[0]

    return {
        "current_status": (
            "up" if latest["is_success"] else "down"
        ),
        "last_checked_at": latest["checked_at"],
        "response_time_ms": latest["response_time_ms"],
        "status_code": latest.get("status_code"),
        "error_type": latest.get("error_type"),
        "error_message": latest.get("error_message"),
    }


def format_monitor(monitor: dict) -> dict:
    """Format a database monitor for the frontend."""

    status = monitor_status(monitor["id"])

    return {
        "id": monitor["id"],
        "name": monitor.get("name") or monitor["url"],
        "url": monitor["url"],
        "current_status": status["current_status"],
        "last_checked_at": status["last_checked_at"],
        "response_time_ms": status["response_time_ms"],
        "status_code": status["status_code"],
        "error_type": status["error_type"],
        "error_message": status["error_message"],
        "created_at": monitor.get("created_at"),
    }


def validate_monitor_url(url: str) -> str:
    """Validate URL format before saving it."""

    url = url.strip()
    parsed = urlparse(url)

    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
    ):
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid HTTP or HTTPS URL.",
        )

    try:
        port = parsed.port

        if port is not None and not (1 <= port <= 65535):
            raise ValueError("Invalid port")

    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="The URL contains an invalid port.",
        )

    return url


# --------------------------------------------------
# 6. Basic endpoints
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "API Uptime Monitor API is running."
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------
# 7. Monitor endpoints
# --------------------------------------------------

@app.get("/monitors")
def get_monitors():
    """Return active monitors with their latest check details."""

    response = (
        get_db()
        .table("monitored_urls")
        .select("*")
        .eq("is_active", True)
        .order("id")
        .execute()
    )

    return [
        format_monitor(monitor)
        for monitor in (response.data or [])
    ]


@app.post("/monitors", status_code=201)
def create_monitor(payload: MonitorCreate):
    """Register a website to monitor."""

    name = payload.name.strip()
    url = validate_monitor_url(payload.url)

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Monitor name cannot be empty.",
        )

    db = get_db()

    existing = (
        db.table("monitored_urls")
        .select("id")
        .eq("url", url)
        .limit(1)
        .execute()
    )

    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="This URL is already registered.",
        )

    try:
        response = (
            db.table("monitored_urls")
            .insert({
                "name": name,
                "url": url,
                "is_active": True,
            })
            .execute()
        )

    except Exception as exc:
        message = str(exc).lower()

        if "23505" in message or "duplicate key" in message:
            raise HTTPException(
                status_code=409,
                detail="This URL is already registered.",
            )

        print(f"Could not create monitor: {exc}")

        raise HTTPException(
            status_code=500,
            detail="Could not create monitor. Check the backend logs.",
        )

    if not response.data:
        raise HTTPException(
            status_code=500,
            detail="The monitor could not be saved.",
        )

    return format_monitor(response.data[0])


@app.post("/monitors/{monitor_id}/check")
def check_monitor_now(monitor_id: int):
    """Manually check a website and save its result."""

    db = get_db()

    monitor_response = (
        db.table("monitored_urls")
        .select("*")
        .eq("id", monitor_id)
        .limit(1)
        .execute()
    )

    if not monitor_response.data:
        raise HTTPException(
            status_code=404,
            detail="Monitor not found.",
        )

    monitor = monitor_response.data[0]
    result = check_url(monitor["url"])

    record = {
        "url_id": monitor["id"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "is_success": result["is_success"],
        "status_code": result["status_code"],
        "response_time_ms": result["response_time_ms"],
        "error_type": result["error_type"],
        "error_message": result["error_message"],
    }

    db.table("check_results").insert(record).execute()

    return {
        "monitor_id": monitor_id,
        "url": monitor["url"],
        **result,
    }


@app.delete("/monitors/{monitor_id}")
def delete_monitor(monitor_id: int):
    """Delete a monitor and its check history."""

    db = get_db()

    existing = (
        db.table("monitored_urls")
        .select("id")
        .eq("id", monitor_id)
        .limit(1)
        .execute()
    )

    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail="Monitor not found.",
        )

    try:
        db.table("check_results").delete().eq(
            "url_id", monitor_id
        ).execute()

        db.table("monitored_urls").delete().eq(
            "id", monitor_id
        ).execute()

    except Exception as exc:
        print(f"Could not delete monitor: {exc}")

        raise HTTPException(
            status_code=500,
            detail="Could not delete monitor. Check the backend logs.",
        )

    return {
        "success": True,
        "message": "Monitor and its history deleted.",
    }


@app.get("/monitors/{monitor_id}/checks")
def get_monitor_checks(monitor_id: int):
    """Return recent check history for a monitor."""

    db = get_db()

    existing = (
        db.table("monitored_urls")
        .select("id")
        .eq("id", monitor_id)
        .limit(1)
        .execute()
    )

    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail="Monitor not found.",
        )

    response = (
        db.table("check_results")
        .select("*")
        .eq("url_id", monitor_id)
        .order("checked_at", desc=True)
        .limit(100)
        .execute()
    )

    return [
        {
            "id": item["id"],
            "checked_at": item["checked_at"],
            "is_up": item["is_success"],
            "status_code": item["status_code"],
            "response_time_ms": item["response_time_ms"],
            "error_type": item.get("error_type"),
            "error_message": item.get("error_message"),
        }
        for item in (response.data or [])
    ]


# --------------------------------------------------
# 8. Browser activity endpoints
# --------------------------------------------------

@app.post("/browser-activity")
def update_browser_activity(payload: BrowserActivityUpdate):
    """Receive domains currently open in the Chrome extension."""

    db = get_db()
    incoming = {}

    for item in payload.domains:
        domain = item.domain.strip().lower().rstrip(".")

        if (
            not domain
            or "/" in domain
            or ":" in domain
            or " " in domain
        ):
            continue

        if item.tab_count > 0:
            incoming[domain] = item.tab_count

    now = datetime.now(timezone.utc).isoformat()

    existing_response = (
        db.table("browser_activity")
        .select("domain")
        .execute()
    )

    existing_domains = {
        row["domain"]
        for row in (existing_response.data or [])
    }

    for domain, tab_count in incoming.items():
        db.table("browser_activity").upsert(
            {
                "domain": domain,
                "is_open": True,
                "tab_count": tab_count,
                "last_seen_at": now,
                "updated_at": now,
            },
            on_conflict="domain",
        ).execute()

    for domain in existing_domains - set(incoming):
        db.table("browser_activity").update(
            {
                "is_open": False,
                "tab_count": 0,
                "updated_at": now,
            }
        ).eq("domain", domain).execute()

    return {
        "success": True,
        "domains_open": len(incoming),
    }


@app.get("/browser-activity")
def get_browser_activity():
    """Return browser activity and expire stale heartbeats."""

    db = get_db()

    response = (
        db.table("browser_activity")
        .select("*")
        .order("domain")
        .execute()
    )

    now = datetime.now(timezone.utc)
    results = []

    for row in response.data or []:
        is_open = bool(row.get("is_open"))
        tab_count = row.get("tab_count", 0)
        last_seen = row.get("last_seen_at")

        if is_open:
            try:
                if not last_seen:
                    raise ValueError("Missing heartbeat")

                last_seen_time = datetime.fromisoformat(
                    last_seen.replace("Z", "+00:00")
                )

                if last_seen_time.tzinfo is None:
                    last_seen_time = last_seen_time.replace(
                        tzinfo=timezone.utc
                    )

                if (now - last_seen_time).total_seconds() > 90:
                    is_open = False

            except (ValueError, AttributeError):
                is_open = False

        if not is_open and row.get("is_open"):
            db.table("browser_activity").update(
                {
                    "is_open": False,
                    "tab_count": 0,
                    "updated_at": now.isoformat(),
                }
            ).eq("domain", row["domain"]).execute()

        results.append({
            "domain": row["domain"],
            "is_open": is_open,
            "tab_count": tab_count if is_open else 0,
            "last_seen_at": last_seen,
        })

    return {"domains": results}
