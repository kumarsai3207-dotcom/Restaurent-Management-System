/**
 * Kitchen Display System (KDS) View: filter active orders and advance tickets with one click.
 */

import { apiRequest, escapeHtml } from "/js/api.js";

const NEXT_STATUS_ACTION = {
  Queued: { next: "Preparing", label: "🔥 Start Preparing" },
  Preparing: { next: "Ready", label: "✅ Mark Ready" },
  Ready: { next: "Served", label: "🍽️ Mark Served" },
};

export function createKdsController(state, showToast, refreshAllOrders) {
  const filterPills = document.getElementById("kdsFilterPills");
  const kdsGrid = document.getElementById("kdsGrid");
  const kdsBadge = document.getElementById("kdsBadge");
  let activeFilter = "ACTIVE";

  function minutesSince(isoStr) {
    const diff = Math.max(0, Math.floor((Date.now() - new Date(isoStr).getTime()) / 60000));
    return `${diff}m ago`;
  }

  function render() {
    const allOrders = state.orders || [];
    const activeCount = allOrders.filter((o) => ["Queued", "Preparing", "Ready"].includes(o.status)).length;
    kdsBadge.textContent = String(activeCount);

    const filtered = allOrders.filter((o) => {
      if (activeFilter === "ACTIVE") return ["Queued", "Preparing", "Ready"].includes(o.status);
      return o.status === activeFilter;
    });

    if (!filtered.length) {
      kdsGrid.innerHTML = `<div class="card" style="background:#1c1917;color:#d6d3d1;border-color:#44403c;">No orders in "${escapeHtml(activeFilter)}" queue right now.</div>`;
      return;
    }

    kdsGrid.innerHTML = filtered
      .map((o) => {
        const modeTag =
          o.order_mode === "dine_in"
            ? `🪑 Table ${escapeHtml(o.table_number)}`
            : `🛍️ Takeaway (${escapeHtml(o.pickup_slot)})`;
        const action = NEXT_STATUS_ACTION[o.status];
        const itemsHtml = o.items
          .map((it) => {
            const addons = it.selected_addons.length
              ? `<div class="kds-item-note">+ ${it.selected_addons.map((a) => escapeHtml(a.name)).join(", ")}</div>`
              : "";
            const notes = it.notes ? `<div class="kds-item-note">📝 ${escapeHtml(it.notes)}</div>` : "";
            return `
              <li class="kds-item-line">
                <div><strong>${it.quantity}× ${escapeHtml(it.item_name)}</strong> <span class="badge badge-spice">${escapeHtml(it.spice_preference)}</span></div>
                ${addons}
                ${notes}
              </li>`;
          })
          .join("");

        return `
          <article class="kds-ticket status-${escapeHtml(o.status)}">
            <div>
              <div class="kds-ticket-head">
                <div>
                  <strong style="font-size:1.05rem;">${escapeHtml(o.order_number)}</strong>
                  <div style="font-size:0.82rem;color:#d6d3d1;">${modeTag} • ${escapeHtml(o.customer_name)}</div>
                </div>
                <div style="text-align:right;">
                  <span class="badge badge-info">${escapeHtml(o.status)}</span>
                  <div style="font-size:0.75rem;color:#a8a29e;margin-top:0.2rem;">⏱️ ${minutesSince(o.created_at)}</div>
                </div>
              </div>
              <ul class="kds-items" style="margin-top:0.65rem;">${itemsHtml}</ul>
              ${o.special_instructions ? `<div class="kds-item-note" style="margin-top:0.5rem;">⚠️ Order Note: ${escapeHtml(o.special_instructions)}</div>` : ""}
            </div>
            <div class="kds-actions">
              ${
                action
                  ? `<button class="btn btn-primary kds-advance-btn" data-oid="${o.id}" data-next="${action.next}">${action.label}</button>`
                  : `<span style="color:#a8a29e;font-size:0.82rem;">Completed</span>`
              }
              ${
                ["Queued", "Preparing"].includes(o.status)
                  ? `<button class="btn btn-secondary kds-advance-btn" data-oid="${o.id}" data-next="Cancelled">Cancel</button>`
                  : ""
              }
            </div>
          </article>
        `;
      })
      .join("");
  }

  filterPills.addEventListener("click", (e) => {
    const btn = e.target.closest(".kds-filter");
    if (!btn) return;
    activeFilter = btn.dataset.status;
    filterPills.querySelectorAll(".kds-filter").forEach((b) => b.classList.toggle("active", b === btn));
    render();
  });

  kdsGrid.addEventListener("click", async (e) => {
    const btn = e.target.closest(".kds-advance-btn");
    if (!btn) return;
    btn.disabled = true;
    try {
      const data = await apiRequest(`/api/orders/${btn.dataset.oid}/status`, {
        method: "PATCH",
        body: { status: btn.dataset.next },
      });
      showToast(`${data.order.order_number} -> ${data.order.status}`, "success");
      await refreshAllOrders();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });

  return { render };
}
