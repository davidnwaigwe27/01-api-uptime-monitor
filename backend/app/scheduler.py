
import threading
import time
from datetime import datetime, timezone

from .checker import check_url


def run_check_for_monitor(supabase, monitor):
    """Check one monitored website and save the result to Supabase."""

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

    # Save the check result to the database.
    supabase.table("check_results").insert(record).execute()

    status = "UP" if result["is_success"] else "DOWN"

    # Print detailed debugging information in the terminal.
    print(
        f"Checked {monitor['url']}: {status} "
        f"| HTTP: {result['status_code']} "
        f"| Response time: {result['response_time_ms']} ms "
        f"| Error: {result['error_type']} "
        f"| Details: {result['error_message']}"
    )


def check_all_monitors(supabase):
    """Check every active monitor and save its result."""

    response = (
        supabase.table("monitored_urls")
        .select("id, url")
        .eq("is_active", True)
        .execute()
    )

    monitors = response.data or []

    for monitor in monitors:
        try:
            run_check_for_monitor(supabase, monitor)

        except Exception as exc:
            print(
                f"Could not check "
                f"{monitor.get('url', 'unknown URL')}: {exc}"
            )


def run_forever(supabase, interval_seconds=60):
    """Run website checks repeatedly in a background thread."""

    def loop():
        while True:
            try:
                check_all_monitors(supabase)

            except Exception as exc:
                print(f"Scheduler error: {exc}")

            time.sleep(interval_seconds)

    thread = threading.Thread(
        target=loop,
        daemon=True,
        name="uptime-monitor-scheduler",
    )

    thread.start()

    print(
        f"Monitor scheduler started "
        f"(every {interval_seconds} seconds)."
    )

    return thread
