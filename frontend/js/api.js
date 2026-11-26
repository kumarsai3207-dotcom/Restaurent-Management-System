/**
 * API client, currency formatter, and SSE real-time subscription with clean polling fallback.
 */

export function formatINR(paise) {
  const amount = (Number(paise || 0) / 100).toFixed(2);
  return `₹${amount}`;
}

export function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export async function apiRequest(url, options = {}) {
  const opts = {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  const resp = await fetch(url, opts);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error(data.error || `Request failed (${resp.status})`);
    err.status = resp.status;
    err.details = data.details;
    throw err;
  }
  return data;
}

export class RealtimeClient {
  constructor(onEvent, onStatusChange) {
    this.onEvent = onEvent;
    this.onStatusChange = onStatusChange;
    this.eventSource = null;
    this.pollTimer = null;
  }

  start() {
    if (typeof EventSource === "undefined") {
      this._startPolling();
      return;
    }

    try {
      const es = new EventSource("/api/events");
      this.eventSource = es;

      es.addEventListener("connected", () => {
        this._stopPolling();
        this.onStatusChange("live");
      });

      for (const evtName of ["session.updated", "session.checked_out", "order.created", "order.updated", "menu.updated"]) {
        es.addEventListener(evtName, (e) => {
          try {
            const parsed = JSON.parse(e.data);
            this.onEvent(evtName, parsed.payload);
          } catch {
            // ignore malformed frames
          }
        });
      }

      es.onerror = () => {
        this.onStatusChange("polling");
        this._startPolling();
      };
    } catch {
      this._startPolling();
    }
  }

  _startPolling() {
    if (this.pollTimer) return;
    this.onStatusChange("polling");
    this.pollTimer = window.setInterval(() => {
      this.onEvent("poll.tick", {});
    }, 4000);
  }

  _stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
}
