# API Contract

Status values for current_status: "up", "down", "unknown" (unknown = not checked yet).
All errors reply as: {"detail": "message"}

## POST /monitors  (add a URL)
Dashboard sends: {"name": "My Site", "url": "https://example.com"}
You reply (201): {"id": 1, "name": "My Site", "url": "https://example.com", "current_status": "unknown", "last_checked_at": null, "created_at": "2026-10-20T10:00:00Z"}
Error (422): {"detail": "Invalid URL"}
Error (409): {"detail": "URL already registered"}

## GET /monitors  (list all URLs)
Dashboard sends: nothing
You reply (200): [
  {"id": 1, "name": "My Site", "url": "https://example.com", "current_status": "up", "last_checked_at": "2026-10-20T10:05:00Z", "created_at": "2026-10-20T10:00:00Z"}
]
If no URLs are registered yet, you reply (200): []

## DELETE /monitors/{id}  (remove a URL)
Dashboard sends: nothing (the id is in the address, e.g. /monitors/1)
You reply (204): nothing (done, no content)
Error (404): {"detail": "Monitor not found"}

## GET /monitors/{id}/checks  (check history for one URL)
Dashboard sends: nothing (the id is in the address, e.g. /monitors/1/checks)
You reply (200): [
  {"id": 1, "status_code": 200, "response_time_ms": 143, "is_up": true, "checked_at": "2026-10-20T10:10:00Z"}
]
Error (404): {"detail": "Monitor not found"}