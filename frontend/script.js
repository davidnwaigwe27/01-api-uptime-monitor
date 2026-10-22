
const API_BASE_URL = "http://127.0.0.1:8000";

// HTML elements
const monitorForm = document.getElementById("monitor-form");
const nameInput = document.getElementById("monitor-name");
const urlInput = document.getElementById("monitor-url");
const openFormButton = document.getElementById("open-form-button");
const cancelFormButton = document.getElementById("cancel-form-button");
const feedback = document.getElementById("feedback");

const monitorList = document.getElementById("monitor-list");
const historyList = document.getElementById("history-list");
const historyDescription = document.getElementById("history-description");

const totalCount = document.getElementById("total-count");
const upCount = document.getElementById("up-count");
const downCount = document.getElementById("down-count");
const avgResponse = document.getElementById("avg-response");

const connectionStatus = document.getElementById("connection-status");
const connectionDot = document.querySelector(".status-dot");

let monitors = [];
let selectedMonitorId = null;


// ---------------------------------------------
// General helpers
// ---------------------------------------------

function showFeedback(message, type = "") {
    feedback.textContent = message;
    feedback.className = type;
}

function clearFeedback() {
    feedback.textContent = "";
    feedback.className = "";
}

function setConnection(connected) {
    connectionStatus.textContent = connected
        ? "Backend connected"
        : "Backend unavailable";

    if (connectionDot) {
        connectionDot.style.background = connected
            ? "#35c78a"
            : "#e05a67";
    }
}

function formatDate(value) {
    if (!value) return "Never";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "Unknown";

    return date.toLocaleString();
}

function formatResponseTime(value) {
    if (value === null || value === undefined || value === "") {
        return "—";
    }

    const milliseconds = Number(value);

    if (!Number.isFinite(milliseconds)) return "—";

    return `${Math.round(milliseconds)} ms`;
}

function normalizeStatus(monitor) {
    const status = String(monitor.current_status || "").toLowerCase();

    if (status === "up" || status === "down") {
        return status;
    }

    return "unknown";
}

function statusBadge(status) {
    const normalized = ["up", "down", "unknown"].includes(status)
        ? status
        : "unknown";

    const labels = {
        up: "UP",
        down: "DOWN",
        unknown: "UNKNOWN"
    };

    const badge = document.createElement("span");
    badge.className = `status-badge status-${normalized}`;
    badge.textContent = labels[normalized];

    return badge;
}

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers: {
            ...(options.body
                ? { "Content-Type": "application/json" }
                : {}),
            ...options.headers
        }
    });

    if (!response.ok) {
        let message = `Request failed (${response.status})`;

        try {
            const errorData = await response.json();
            message = errorData.detail || message;
        } catch {
            // Keep the default message if the response isn't JSON.
        }

        throw new Error(message);
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}


// ---------------------------------------------
// Explanation beneath each monitored URL
// ---------------------------------------------

function getMonitorMessage(monitor) {
    const status = normalizeStatus(monitor);
    const errorType = monitor.error_type;
    const code = monitor.status_code;

    if (status === "unknown") {
        return {
            text: "Waiting for the first website check.",
            type: "unknown"
        };
    }

    if (status === "down") {
        if (errorType === "ReservedExampleDomain") {
            return {
                text: "Reserved example domain — not intended for real monitoring.",
                type: "down"
            };
        }

        if (errorType === "InvalidOrPrivateURL") {
            return {
                text: "This URL doesn't exist or cannot be reached.",
                type: "down"
            };
        }

        if (errorType === "Timeout") {
            return {
                text: "Request timed out — the website did not respond in time.",
                type: "down"
            };
        }

        if (errorType === "HTTPServerError") {
            return {
                text: code
                    ? `Server error (HTTP ${code}).`
                    : "The website returned a server error.",
                type: "down"
            };
        }

        if (errorType) {
            return {
                text: monitor.error_message || "The website could not be reached.",
                type: "down"
            };
        }

        if (code !== null && code !== undefined) {
            return {
                text: `Website check failed (HTTP ${code}).`,
                type: "down"
            };
        }

        return {
            text: monitor.error_message || "The website could not be reached.",
            type: "down"
        };
    }

    if (status === "up" && code === 403) {
        return {
            text: "Website responded, but access was denied (HTTP 403).",
            type: "up"
        };
    }

    if (status === "up" && code === 404) {
        return {
            text: "The server responded, but this page was not found (HTTP 404).",
            type: "up"
        };
    }

    return {
        text: "Website is reachable.",
        type: "up"
    };
}

function appendMonitorMessage(urlCell, monitor) {
    const message = getMonitorMessage(monitor);

    const messageElement = document.createElement("div");
    messageElement.className = `monitor-message monitor-message-${message.type}`;
    messageElement.textContent = message.text;

    // Inline styles keep this feature working without requiring CSS changes.
    messageElement.style.fontSize = "12px";
    messageElement.style.marginTop = "5px";
    messageElement.style.lineHeight = "1.5";
    messageElement.style.overflowWrap = "anywhere";

    if (message.type === "down") {
        messageElement.style.color = "#e05a67";
    } else if (message.type === "up") {
        messageElement.style.color = "#35c78a";
    } else {
        messageElement.style.color = "#999999";
    }

    urlCell.appendChild(messageElement);
}


// ---------------------------------------------
// Add monitor form
// ---------------------------------------------

openFormButton.addEventListener("click", () => {
    clearFeedback();
    monitorForm.hidden = false;
    nameInput.focus();
});

cancelFormButton.addEventListener("click", () => {
    monitorForm.reset();
    monitorForm.hidden = true;
    clearFeedback();
});

monitorForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFeedback();

    const name = nameInput.value.trim();
    const url = urlInput.value.trim();

    if (!name) {
        showFeedback("Please enter a monitor name.", "error");
        nameInput.focus();
        return;
    }

    let parsedURL;

    try {
        parsedURL = new URL(url);
    } catch {
        showFeedback(
            "Please enter a valid URL, such as https://example.com.",
            "error"
        );
        urlInput.focus();
        return;
    }

    if (!["http:", "https:"].includes(parsedURL.protocol)) {
        showFeedback("Only HTTP and HTTPS URLs are supported.", "error");
        urlInput.focus();
        return;
    }

    const submitButton = monitorForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.textContent = "Saving...";

    try {
        await apiRequest("/monitors", {
            method: "POST",
            body: JSON.stringify({
                name,
                url: parsedURL.href
            })
        });

        monitorForm.reset();
        monitorForm.hidden = true;

        showFeedback(
            "Monitor added successfully. Waiting for the first check.",
            "success"
        );

        await loadMonitors();
    } catch (error) {
        showFeedback(
            `Could not add monitor: ${error.message}`,
            "error"
        );
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Save monitor";
    }
});


// ---------------------------------------------
// Load monitors from FastAPI
// ---------------------------------------------

async function loadMonitors() {
    try {
        const data = await apiRequest("/monitors");

        if (!Array.isArray(data)) {
            throw new Error("The backend returned an unexpected monitor list.");
        }

        monitors = data;
        setConnection(true);

        renderMonitors();
        updateSummary();

        if (selectedMonitorId !== null) {
            const stillExists = monitors.some(
                (monitor) => String(monitor.id) === String(selectedMonitorId)
            );

            if (stillExists) {
                await loadHistory(selectedMonitorId);
            } else {
                selectedMonitorId = null;
                resetHistory();
            }
        }
    } catch (error) {
        setConnection(false);
        monitorList.replaceChildren();

        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 5;
        cell.className = "empty-state";
        cell.textContent =
            "Cannot connect to the backend. Start FastAPI and check the connection.";

        row.appendChild(cell);
        monitorList.appendChild(row);

        totalCount.textContent = "—";
        upCount.textContent = "—";
        downCount.textContent = "—";
        avgResponse.textContent = "—";

        console.error("Failed to load monitors:", error);
    }
}

function renderMonitors() {
    monitorList.replaceChildren();

    if (monitors.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 5;
        cell.className = "empty-state";
        cell.textContent =
            "No monitors yet. Add your first endpoint to get started.";

        row.appendChild(cell);
        monitorList.appendChild(row);
        return;
    }

    monitors.forEach((monitor) => {
        const row = document.createElement("tr");

        // Monitor name
        const nameCell = document.createElement("td");
        nameCell.textContent = monitor.name || "Unnamed monitor";

        // URL and explanation
        const urlCell = document.createElement("td");
        const urlLink = document.createElement("a");

        urlLink.textContent = monitor.url || "No URL";
        urlLink.href = "#";

        try {
            const parsed = new URL(monitor.url);

            if (["http:", "https:"].includes(parsed.protocol)) {
                urlLink.href = parsed.href;
                urlLink.target = "_blank";
                urlLink.rel = "noopener noreferrer";
            }
        } catch {
            // Display malformed URLs as text.
        }

        urlCell.appendChild(urlLink);
        appendMonitorMessage(urlCell, monitor);

        // Status badge
        const statusCell = document.createElement("td");
        statusCell.appendChild(statusBadge(normalizeStatus(monitor)));

        // Last checked
        const checkedCell = document.createElement("td");
        checkedCell.textContent = formatDate(monitor.last_checked_at);

        // Actions
        const actionsCell = document.createElement("td");

        const historyButton = document.createElement("button");
        historyButton.type = "button";
        historyButton.className = "action-button";
        historyButton.textContent = "History";

        historyButton.addEventListener("click", () => {
            selectedMonitorId = monitor.id;
            loadHistory(monitor.id);

            document.getElementById("history").scrollIntoView({
                behavior: "smooth",
                block: "start"
            });
        });

        const checkButton = document.createElement("button");
        checkButton.type = "button";
        checkButton.className = "action-button";
        checkButton.textContent = "Check now";
        checkButton.style.marginLeft = "6px";

        checkButton.addEventListener("click", async () => {
            checkButton.disabled = true;
            checkButton.textContent = "Checking...";

            try {
                await apiRequest(
                    `/monitors/${encodeURIComponent(monitor.id)}/check`,
                    { method: "POST" }
                );

                await loadMonitors();

                showFeedback(
                    `Check completed for ${monitor.name || monitor.url}.`,
                    "success"
                );
            } catch (error) {
                showFeedback(
                    `Could not check website: ${error.message}`,
                    "error"
                );
            } finally {
                checkButton.disabled = false;
                checkButton.textContent = "Check now";
            }
        });

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "action-button delete-button";
        deleteButton.textContent = "Delete";
        deleteButton.style.marginLeft = "6px";

        deleteButton.addEventListener("click", () => deleteMonitor(monitor));

        actionsCell.append(
            historyButton,
            checkButton,
            deleteButton
        );

        row.append(
            nameCell,
            urlCell,
            statusCell,
            checkedCell,
            actionsCell
        );

        monitorList.appendChild(row);
    });
}


// ---------------------------------------------
// Dashboard summary cards
// ---------------------------------------------

function updateSummary() {
    const up = monitors.filter(
        (monitor) => normalizeStatus(monitor) === "up"
    ).length;

    const down = monitors.filter(
        (monitor) => normalizeStatus(monitor) === "down"
    ).length;

    totalCount.textContent = monitors.length;
    upCount.textContent = up;
    downCount.textContent = down;

    const responseTimes = monitors
        .map((monitor) => Number(monitor.response_time_ms))
        .filter((value) => Number.isFinite(value) && value >= 0);

    if (responseTimes.length > 0) {
        const average = responseTimes.reduce(
            (sum, value) => sum + value,
            0
        ) / responseTimes.length;

        avgResponse.textContent = `${Math.round(average)} ms`;
    } else {
        avgResponse.textContent = "—";
    }
}


// ---------------------------------------------
// Delete monitor
// ---------------------------------------------

async function deleteMonitor(monitor) {
    const name = monitor.name || monitor.url || "this monitor";

    if (!window.confirm(`Are you sure you want to delete "${name}"?`)) {
        return;
    }

    try {
        await apiRequest(
            `/monitors/${encodeURIComponent(monitor.id)}`,
            { method: "DELETE" }
        );

        if (String(selectedMonitorId) === String(monitor.id)) {
            selectedMonitorId = null;
            resetHistory();
        }

        showFeedback("Monitor deleted successfully.", "success");
        await loadMonitors();
    } catch (error) {
        showFeedback(
            `Could not delete monitor: ${error.message}`,
            "error"
        );
    }
}


// ---------------------------------------------
// Check history
// ---------------------------------------------

function resetHistory() {
    historyDescription.textContent =
        "Select a monitor to view its history.";

    historyList.replaceChildren();

    const row = document.createElement("tr");
    const cell = document.createElement("td");

    cell.colSpan = 4;
    cell.className = "empty-state";
    cell.textContent = "No check history selected.";

    row.appendChild(cell);
    historyList.appendChild(row);
}

async function loadHistory(monitorId) {
    const monitor = monitors.find(
        (item) => String(item.id) === String(monitorId)
    );

    historyDescription.textContent = monitor
        ? `Recent checks for ${monitor.name || monitor.url}`
        : "Loading check history...";

    historyList.replaceChildren();

    const loadingRow = document.createElement("tr");
    const loadingCell = document.createElement("td");

    loadingCell.colSpan = 4;
    loadingCell.className = "empty-state";
    loadingCell.textContent = "Loading check history...";

    loadingRow.appendChild(loadingCell);
    historyList.appendChild(loadingRow);

    try {
        const data = await apiRequest(
            `/monitors/${encodeURIComponent(monitorId)}/checks`
        );

        if (!Array.isArray(data)) {
            throw new Error("The backend returned an unexpected history format.");
        }

        if (String(selectedMonitorId) !== String(monitorId)) {
            return;
        }

        historyList.replaceChildren();

        if (data.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");

            cell.colSpan = 4;
            cell.className = "empty-state";
            cell.textContent =
                "No checks have been recorded for this monitor yet.";

            row.appendChild(cell);
            historyList.appendChild(row);
            return;
        }

        data.forEach((check) => {
            const row = document.createElement("tr");

            const dateCell = document.createElement("td");
            dateCell.textContent = formatDate(check.checked_at);

            const statusCell = document.createElement("td");
            const isUp = check.is_up === true;
            const isDown = check.is_up === false;

            statusCell.appendChild(
                statusBadge(isUp ? "up" : isDown ? "down" : "unknown")
            );

            const codeCell = document.createElement("td");
            codeCell.textContent = check.status_code ?? "—";

            const timeCell = document.createElement("td");
            timeCell.textContent = formatResponseTime(
                check.response_time_ms
            );

            row.append(dateCell, statusCell, codeCell, timeCell);
            historyList.appendChild(row);
        });
    } catch (error) {
        if (String(selectedMonitorId) !== String(monitorId)) {
            return;
        }

        historyList.replaceChildren();

        const row = document.createElement("tr");
        const cell = document.createElement("td");

        cell.colSpan = 4;
        cell.className = "empty-state";
        cell.textContent = `Could not load history: ${error.message}`;

        row.appendChild(cell);
        historyList.appendChild(row);
    }
}


// ---------------------------------------------
// Start the dashboard
// ---------------------------------------------

resetHistory();
loadMonitors();

// Refresh the monitor list every 30 seconds.
window.setInterval(loadMonitors, 30000);
