
"use strict";

// --------------------------------------------------
// 1. API configuration
// --------------------------------------------------

const API_BASE_URL =
    "https://zero1-api-uptime-monitor-backend.onrender.com";

// --------------------------------------------------
// 2. DOM elements
// --------------------------------------------------

const monitorForm = document.getElementById("monitor-form");
const urlInput = document.getElementById("monitor-url");
const nameInput = document.getElementById("monitor-name");
const monitorList = document.getElementById("monitor-list");
const historyList = document.getElementById("history-list");
const historyDescription = document.getElementById("history-description");
const feedback = document.getElementById("feedback");

const openFormButton = document.getElementById("open-form-button");
const cancelFormButton = document.getElementById("cancel-form-button");

const totalCount = document.getElementById("total-count");
const upCount = document.getElementById("up-count");
const downCount = document.getElementById("down-count");
const avgResponse = document.getElementById("avg-response");

// --------------------------------------------------
// 3. State
// --------------------------------------------------

let monitors = [];
let selectedMonitorId = null;

// --------------------------------------------------
// 4. User-friendly feedback
// --------------------------------------------------

function showFeedback(message, type = "info") {
    if (!feedback) return;

    // Never show raw backend errors to dashboard users.
    const safeMessages = {
        success: message,
        error: "Unable to complete your request. Please try again.",
        info: message,
    };

    feedback.textContent =
        safeMessages[type] || safeMessages.info;

    feedback.dataset.type = type;
    feedback.hidden = false;
}

function clearFeedback() {
    if (!feedback) return;

    feedback.textContent = "";
    feedback.hidden = true;
}

// --------------------------------------------------
// 5. API request helper
// --------------------------------------------------

async function apiRequest(endpoint, options = {}) {
    let response;

    try {
        response = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                ...(options.headers || {}),
            },
        });
    } catch (error) {
        console.error("API request failed:", error);
        throw new Error("NETWORK_ERROR");
    }

    if (!response.ok) {
        let detail = "";

        try {
            const data = await response.json();
            detail = data.detail || "";
        } catch {
            // Response may not contain JSON.
        }

        console.error("API error:", response.status, detail);

        const error = new Error("API_ERROR");
        error.status = response.status;
        error.detail = detail;
        throw error;
    }

    if (response.status === 204) return null;

    return response.json();
}

// --------------------------------------------------
// 6. Form visibility
// --------------------------------------------------

function openMonitorForm() {
    if (monitorForm) {
        monitorForm.hidden = false;
    }

    if (openFormButton) {
        openFormButton.hidden = true;
    }

    nameInput?.focus();
}

function closeMonitorForm() {
    if (monitorForm) {
        monitorForm.reset();
        monitorForm.hidden = true;
    }

    if (openFormButton) {
        openFormButton.hidden = false;
    }

    clearFeedback();
}

openFormButton?.addEventListener("click", openMonitorForm);
cancelFormButton?.addEventListener("click", closeMonitorForm);

// --------------------------------------------------
// 7. Safe HTML rendering
// --------------------------------------------------

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
    })[char]);
}

function formatDate(value) {
    if (!value) return "Never";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "Never";

    return date.toLocaleString();
}

function formatResponseTime(value) {
    if (value === null || value === undefined) return "—";

    return `${Number(value).toFixed(0)} ms`;
}

function statusLabel(status) {
    const normalized = String(status || "unknown").toLowerCase();

    if (normalized === "up") return "UP";
    if (normalized === "down") return "DOWN";

    return "UNKNOWN";
}

// --------------------------------------------------
// 8. Dashboard statistics
// --------------------------------------------------

function updateStatistics() {
    const up = monitors.filter(
        (monitor) => monitor.current_status === "up"
    ).length;

    const down = monitors.filter(
        (monitor) => monitor.current_status === "down"
    ).length;

    const responseTimes = monitors
        .map((monitor) => monitor.response_time_ms)
        .filter((value) => value !== null && value !== undefined)
        .map(Number)
        .filter(Number.isFinite);

    const average = responseTimes.length
        ? responseTimes.reduce((sum, value) => sum + value, 0) /
          responseTimes.length
        : null;

    if (totalCount) totalCount.textContent = monitors.length;
    if (upCount) upCount.textContent = up;
    if (downCount) downCount.textContent = down;

    if (avgResponse) {
        avgResponse.textContent =
            average === null ? "—" : `${Math.round(average)} ms`;
    }
}

// --------------------------------------------------
// 9. Render monitors
// --------------------------------------------------

function renderMonitors() {
    if (!monitorList) return;

    if (!monitors.length) {
        monitorList.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    No monitors yet. Add a website to get started.
                </td>
            </tr>
        `;

        updateStatistics();
        return;
    }

    monitorList.innerHTML = monitors.map((monitor) => {
        const status = String(
            monitor.current_status || "unknown"
        ).toLowerCase();

        const safeStatus = ["up", "down", "unknown"].includes(status)
            ? status
            : "unknown";

        return `
            <tr>
                <td>${escapeHTML(monitor.name || monitor.url)}</td>

                <td>
                    <a href="${escapeHTML(monitor.url)}"
                       target="_blank"
                       rel="noopener noreferrer">
                        ${escapeHTML(monitor.url)}
                    </a>
                </td>

                <td>
                    <span class="status-badge status-${safeStatus}">
                        ${statusLabel(safeStatus)}
                    </span>
                </td>

                <td>${formatResponseTime(monitor.response_time_ms)}</td>

                <td>${escapeHTML(formatDate(monitor.last_checked_at))}</td>

                <td>
                    <button type="button"
                            class="view-history-button"
                            data-action="history"
                            data-id="${escapeHTML(monitor.id)}">
                        History
                    </button>

                    <button type="button"
                            class="check-monitor-button"
                            data-action="check"
                            data-id="${escapeHTML(monitor.id)}">
                        Check now
                    </button>

                    <button type="button"
                            class="delete-monitor-button"
                            data-action="delete"
                            data-id="${escapeHTML(monitor.id)}">
                        Delete
                    </button>
                </td>
            </tr>
        `;
    }).join("");

    updateStatistics();
}

// --------------------------------------------------
// 10. Load monitors
// --------------------------------------------------

async function loadMonitors() {
    try {
        const data = await apiRequest("/monitors");

        monitors = Array.isArray(data) ? data : [];
        renderMonitors();

        if (selectedMonitorId !== null) {
            const stillExists = monitors.some(
                (monitor) =>
                    String(monitor.id) === String(selectedMonitorId)
            );

            if (stillExists) {
                await loadHistory(selectedMonitorId);
            } else {
                clearHistory();
            }
        }

        return true;
    } catch (error) {
        console.error("Could not load monitors:", error);

        // Do not replace the whole dashboard with a technical error.
        if (monitorList && !monitors.length) {
            monitorList.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-state">
                        Monitors are temporarily unavailable.
                        Please try again shortly.
                    </td>
                </tr>
            `;
        }

        showFeedback(
            "Unable to load monitors right now. Please try again.",
            "error"
        );

        return false;
    }
}

// --------------------------------------------------
// 11. Add monitor
// --------------------------------------------------

monitorForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFeedback();

    const name = nameInput?.value.trim() || "";
    const url = urlInput?.value.trim() || "";

    if (!name || !url) {
        showFeedback("Enter a monitor name and website URL.", "error");
        return;
    }

    let parsedURL;

    try {
        parsedURL = new URL(url);
    } catch {
        showFeedback("Please enter a valid website URL.", "error");
        return;
    }

    if (!["http:", "https:"].includes(parsedURL.protocol)) {
        showFeedback("Use a website URL starting with http:// or https://.", "error");
        return;
    }

    const submitButton = monitorForm.querySelector(
        'button[type="submit"]'
    );

    if (submitButton) submitButton.disabled = true;

    try {
        await apiRequest("/monitors", {
            method: "POST",
            body: JSON.stringify({ name, url }),
        });

        closeMonitorForm();
        showFeedback("Monitor added successfully.", "success");

        await loadMonitors();
    } catch (error) {
        console.error("Could not add monitor:", error);

        if (error.status === 409) {
            showFeedback("This website is already being monitored.", "error");
        } else if (error.status === 422) {
            showFeedback("Please check the monitor name and website URL.", "error");
        } else {
            showFeedback(
                "Unable to add this monitor right now. Please try again.",
                "error"
            );
        }
    } finally {
        if (submitButton) submitButton.disabled = false;
    }
});

// --------------------------------------------------
// 12. Delete monitor
// --------------------------------------------------

async function deleteMonitor(monitorId) {
    if (!confirm("Are you sure you want to delete this monitor?")) {
        return;
    }

    clearFeedback();

    try {
        await apiRequest(`/monitors/${encodeURIComponent(monitorId)}`, {
            method: "DELETE",
        });

        if (String(selectedMonitorId) === String(monitorId)) {
            clearHistory();
        }

        showFeedback("Monitor deleted successfully.", "success");
        await loadMonitors();
    } catch (error) {
        console.error("Could not delete monitor:", error);

        showFeedback(
            "Unable to delete this monitor right now. Please try again.",
            "error"
        );
    }
}

// --------------------------------------------------
// 13. Manually check monitor
// --------------------------------------------------

async function checkMonitorNow(monitorId) {
    clearFeedback();

    try {
        await apiRequest(
            `/monitors/${encodeURIComponent(monitorId)}/check`,
            { method: "POST" }
        );

        showFeedback("Website check completed.", "success");

        await loadMonitors();

        if (String(selectedMonitorId) === String(monitorId)) {
            await loadHistory(monitorId);
        }
    } catch (error) {
        console.error("Manual website check failed:", error);

        showFeedback(
            "Unable to check this website right now. Please try again.",
            "error"
        );
    }
}

// --------------------------------------------------
// 14. Monitor table actions
// --------------------------------------------------

monitorList?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");

    if (!button) return;

    const monitorId = button.dataset.id;
    const action = button.dataset.action;

    if (!monitorId) return;

    if (action === "history") {
        await loadHistory(monitorId);
    } else if (action === "check") {
        await checkMonitorNow(monitorId);
    } else if (action === "delete") {
        await deleteMonitor(monitorId);
    }
});

// --------------------------------------------------
// 15. Check history
// --------------------------------------------------

async function loadHistory(monitorId) {
    selectedMonitorId = monitorId;

    const monitor = monitors.find(
        (item) => String(item.id) === String(monitorId)
    );

    if (historyDescription) {
        historyDescription.textContent = monitor
            ? `Recent checks for ${monitor.name || monitor.url}`
            : "Recent website checks";
    }

    if (historyList) {
        historyList.innerHTML = `
            <tr>
                <td colspan="5">Loading check history...</td>
            </tr>
        `;
    }

    try {
        const data = await apiRequest(
            `/monitors/${encodeURIComponent(monitorId)}/checks`
        );

        renderHistory(Array.isArray(data) ? data : []);
    } catch (error) {
        console.error("Could not load check history:", error);

        if (historyList) {
            historyList.innerHTML = `
                <tr>
                    <td colspan="5">
                        Check history is temporarily unavailable.
                    </td>
                </tr>
            `;
        }
    }
}

function renderHistory(history) {
    if (!historyList) return;

    if (!history.length) {
        historyList.innerHTML = `
            <tr>
                <td colspan="5">
                    No check history yet. A result will appear after the first check.
                </td>
            </tr>
        `;
        return;
    }

    historyList.innerHTML = history.map((item) => {
        const isUp = item.is_up === true;
        const status = isUp ? "UP" : "DOWN";

        return `
            <tr>
                <td>${escapeHTML(formatDate(item.checked_at))}</td>
                <td>
                    <span class="status-badge status-${isUp ? "up" : "down"}">
                        ${status}
                    </span>
                </td>
                <td>${escapeHTML(item.status_code ?? "—")}</td>
                <td>${escapeHTML(formatResponseTime(item.response_time_ms))}</td>
                <td>${escapeHTML(item.error_message || "—")}</td>
            </tr>
        `;
    }).join("");
}

function clearHistory() {
    selectedMonitorId = null;

    if (historyDescription) {
        historyDescription.textContent = "Select a monitor to view its check history.";
    }

    if (historyList) {
        historyList.innerHTML = `
            <tr>
                <td colspan="5">Select a monitor to view check history.</td>
            </tr>
        `;
    }
}

// --------------------------------------------------
// 16. Start dashboard
// --------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    loadMonitors();

    // Refresh status and history periodically.
    window.setInterval(() => {
        loadMonitors();
    }, 30000);
});
