import os
from pathlib import Path
from contextlib import asynccontextmanager
from threading import Thread

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from supabase import create_client, Client

# --------------------------------------------------
# 1. Load environment variables from backend/.env
# --------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Missing SUPABASE_URL or SUPABASE_KEY environment variables."
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------------------------------
# 2. Start the existing scheduler in the background
# --------------------------------------------------

scheduler_thread = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler_thread

    from app.scheduler import run_forever

    scheduler_thread = Thread(
        target=run_forever,
        daemon=True,
        name="uptime-monitor-scheduler",
    )
    scheduler_thread.start()

    yield


app = FastAPI(
    title="API Uptime Monitor",
    description="Monitor API availability and response times.",
    version="1.0.0",
    lifespan=lifespan,
)

# --------------------------------------------------
# 3. CORS: allow the deployed Vercel frontend
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://api-uptime-monitor-frontend.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# 4. Request models
# --------------------------------------------------


class MonitorCreate(BaseModel):
    name: str
    url: HttpUrl


# --------------------------------------------------
# 5. Health check
# --------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------
# 6. List monitors
# --------------------------------------------------


@app.get(
    "/monitors",
    responses={
        503: {"description": "Service Unavailable"},
        500: {"description": "Internal Server Error"},
    },
)
def get_monitors():
    try:
        response = (
            supabase.table("monitored_urls")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        monitors = []

        for item in response.data or []:
            monitors.append(
                {
                    "id": item["id"],
                    "name": item.get("name", item.get("url", "")),
                    "url": item["url"],
                    "current_status": "unknown",
                    "last_checked_at": None,
                    "created_at": item.get("created_at"),
                }
            )

        # Get each monitor's most recent check result.
        for monitor in monitors:
            results = (
                supabase.table("check_results")
                .select("*")
                .eq("url_id", monitor["id"])
                .order("checked_at", desc=True)
                .limit(1)
                .execute()
            )

            if results.data:
                latest = results.data[0]
                monitor["current_status"] = (
                    "up" if latest.get("is_success") else "down"
                )
                monitor["last_checked_at"] = latest.get("checked_at")

        return monitors

    except Exception as exc:
        print(f"GET /monitors failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve monitors.",
        )


# --------------------------------------------------
# 7. Create a monitor
# --------------------------------------------------


@app.post(
    "/monitors",
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "URL already registered."},
        500: {"description": "Monitor could not be created."},
    },
)
def create_monitor(monitor: MonitorCreate):
    url = str(monitor.url).rstrip("/")

    try:
        existing = (
            supabase.table("monitored_urls")
            .select("id")
            .eq("url", url)
            .limit(1)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail="URL already registered.",
            )

        response = (
            supabase.table("monitored_urls")
            .insert(
                {
                    "name": monitor.name.strip(),
                    "url": url,
                    "is_active": True,
                }
            )
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=500,
                detail="Monitor could not be created.",
            )

        item = response.data[0]

        return {
            "id": item["id"],
            "name": item.get("name", monitor.name),
            "url": item["url"],
            "current_status": "unknown",
            "last_checked_at": None,
            "created_at": item.get("created_at"),
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"POST /monitors failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not create monitor.",
        )


# --------------------------------------------------
# 8. Delete a monitor
# --------------------------------------------------


@app.delete(
    "/monitors/{monitor_id}",
    responses={
        404: {"description": "Monitor not found."},
        500: {"description": "Could not delete monitor."},
    },
)
def delete_monitor(monitor_id: int):
    try:
        existing = (
            supabase.table("monitored_urls")
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

        # Remove history first if the database has no
        # cascading foreign-key delete configured.
        (
            supabase.table("check_results")
            .delete()
            .eq("url_id", monitor_id)
            .execute()
        )

        (
            supabase.table("monitored_urls")
            .delete()
            .eq("id", monitor_id)
            .execute()
        )

        return {"message": "Monitor deleted successfully."}

    except HTTPException:
        raise
    except Exception as exc:
        print(f"DELETE /monitors/{monitor_id} failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not delete monitor.",
        )


# --------------------------------------------------
# 9. Get check history for a monitor
# --------------------------------------------------


@app.get(
    "/monitors/{monitor_id}/checks",
    responses={
        404: {"description": "Monitor not found."},
        500: {"description": "Could not retrieve check history."},
    },
)
def get_monitor_checks(monitor_id: int):
    try:
        existing = (
            supabase.table("monitored_urls")
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
            supabase.table("check_results")
            .select("*")
            .eq("url_id", monitor_id)
            .order("checked_at", desc=True)
            .limit(100)
            .execute()
        )

        return response.data or []

    except HTTPException:
        raise
    except Exception as exc:
        print(f"GET check history failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve check history.",
        )