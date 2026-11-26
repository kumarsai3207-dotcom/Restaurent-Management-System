/**
 * Admin View: KPI summary metrics, top dishes, menu item creation, price & stock toggles.
 */

import { apiRequest, escapeHtml, formatINR } from "/js/api.js";

export function createAdminController(state, showToast, onMenuChanged) {
  const metricsGrid = document.getElementById("adminMetricsGrid");
  const topDishesTable = document.getElementById("topDishesTable");
  const adminCreateForm = document.getElementById("adminCreateForm");
  const adminMenuTable = document.getElementById("adminMenuTable");

  async function refreshAdminData() {
    const [metricsRes, menuRes] = await Promise.all([
      apiRequest("/api/admin/metrics"),
      apiRequest("/api/menu?include_inactive=1"),
    ]);
    renderMetrics(metricsRes.metrics);
    renderMenuTable(menuRes.items);
  }

  function renderMetrics(m) {
    metricsGrid.innerHTML = `
      <div class="metric-card"><div class="metric-label">Total Revenue</div><div class="metric-value">${formatINR(m.total_revenue_paise)}</div></div>
      <div class="metric-card"><div class="metric-label">Total Orders</div><div class="metric-value">${m.total_orders}</div><div class="muted-label">Dine-In: ${m.dine_in_orders} • Takeaway: ${m.takeaway_orders}</div></div>
      <div class="metric-card"><div class="metric-label">Avg Order Value</div><div class="metric-value">${formatINR(m.avg_order_value_paise)}</div></div>
      <div class="metric-card"><div class="metric-label">Active KDS Tickets</div><div class="metric-value">${m.active_kitchen_orders}</div><div class="muted-label">Active tables: ${m.active_sessions}</div></div>
      <div class="metric-card"><div class="metric-label">Low / Out of Stock</div><div class="metric-value">${m.low_stock_count}</div></div>
    `;

    if (!m.top_dishes.length) {
      topDishesTable.innerHTML = `<p class="muted-label">No dish sales recorded yet.</p>`;
      return;
    }

    topDishesTable.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Dish</th><th>Units Sold</th><th>Revenue</th></tr></thead>
        <tbody>
          ${m.top_dishes
            .map(
              (d) => `
              <tr>
                <td><strong>${escapeHtml(d.item_name)}</strong></td>
                <td>${d.units_sold}</td>
                <td>${formatINR(d.revenue_paise)}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    `;
  }

  function renderMenuTable(items) {
    adminMenuTable.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Dish</th>
            <th>Category</th>
            <th>Dietary / Spice</th>
            <th>Price (₹)</th>
            <th>Stock Qty</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${items
            .map(
              (item) => `
              <tr data-id="${item.id}">
                <td><strong>${escapeHtml(item.image_emoji)} ${escapeHtml(item.name)}</strong></td>
                <td>${escapeHtml(item.category)}</td>
                <td>
                  ${item.is_veg ? "Veg" : "Non-Veg"}${item.is_jain ? " • Jain" : ""}${item.is_vegan ? " • Vegan" : ""}
                  <br><span class="muted-label">${escapeHtml(item.spice_level)}</span>
                </td>
                <td><input type="number" class="input-xs admin-price-input" min="1" value="${Math.round(item.price_paise / 100)}" /></td>
                <td><input type="number" class="input-xs admin-stock-input" min="0" value="${item.stock_count}" /></td>
                <td>
                  <span class="badge ${item.in_stock ? "badge-veg" : "badge-nonveg"}">${item.in_stock ? "In Stock" : "Out of Stock"}</span>
                  ${!item.is_active ? `<span class="badge badge-spice">Hidden</span>` : ""}
                </td>
                <td class="inline-group">
                  <button class="btn btn-secondary btn-sm admin-save-btn">Save</button>
                  <button class="btn btn-ghost btn-sm admin-toggle-stock-btn">${item.in_stock ? "Mark Out" : "Restock"}</button>
                  <button class="btn btn-ghost btn-sm admin-toggle-active-btn">${item.is_active ? "Hide" : "Show"}</button>
                </td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    `;
  }

  adminCreateForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(adminCreateForm);
    try {
      await apiRequest("/api/admin/menu", {
        method: "POST",
        body: {
          name: fd.get("name"),
          category: fd.get("category"),
          description: fd.get("description"),
          price_rupees: Number(fd.get("price_rupees")),
          spice_level: fd.get("spice_level"),
          stock_count: Number(fd.get("stock_count")),
          prep_time_mins: Number(fd.get("prep_time_mins")),
          image_emoji: fd.get("image_emoji") || "🍲",
          is_veg: fd.get("is_veg") === "on",
          is_jain: fd.get("is_jain") === "on",
          is_vegan: fd.get("is_vegan") === "on",
        },
      });
      adminCreateForm.reset();
      showToast("New dish added to menu!", "success");
      await Promise.all([refreshAdminData(), onMenuChanged()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  adminMenuTable.addEventListener("click", async (e) => {
    const row = e.target.closest("tr[data-id]");
    if (!row) return;
    const itemId = Number(row.dataset.id);

    try {
      if (e.target.closest(".admin-save-btn")) {
        const priceRupees = Number(row.querySelector(".admin-price-input").value);
        const stockCount = Number(row.querySelector(".admin-stock-input").value);
        await apiRequest(`/api/admin/menu/${itemId}`, {
          method: "PATCH",
          body: { price_rupees: priceRupees, stock_count: stockCount },
        });
        showToast("Price & stock updated", "success");
      } else if (e.target.closest(".admin-toggle-stock-btn")) {
        const isOutBtn = e.target.textContent.includes("Mark Out");
        await apiRequest(`/api/admin/menu/${itemId}`, {
          method: "PATCH",
          body: isOutBtn ? { in_stock: false } : { in_stock: true, stock_count: Math.max(20, Number(row.querySelector(".admin-stock-input").value)) },
        });
        showToast("Stock availability toggled", "success");
      } else if (e.target.closest(".admin-toggle-active-btn")) {
        const isHiding = e.target.textContent.trim() === "Hide";
        await apiRequest(`/api/admin/menu/${itemId}`, {
          method: "PATCH",
          body: { is_active: !isHiding },
        });
        showToast("Menu visibility updated", "success");
      } else {
        return;
      }
      await Promise.all([refreshAdminData(), onMenuChanged()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  return { refreshAdminData };
}
