/**
 * Customer View: menu browsing, dietary/spice filters, customisation modal,
 * Dine-In / Takeaway mode, shared table session cart, split bill, and live order tracker.
 */

import { apiRequest, escapeHtml, formatINR } from "/js/api.js";

export function createCustomerController(state, showToast, refreshAllOrders) {
  const els = {
    modeDineInBtn: document.getElementById("modeDineInBtn"),
    modeTakeawayBtn: document.getElementById("modeTakeawayBtn"),
    dineInControls: document.getElementById("dineInControls"),
    takeawayControls: document.getElementById("takeawayControls"),
    tableSelect: document.getElementById("tableSelect"),
    customTableInput: document.getElementById("customTableInput"),
    applyModeBtn: document.getElementById("applyModeBtn"),
    pickupSlotSelect: document.getElementById("pickupSlotSelect"),
    applyPickupBtn: document.getElementById("applyPickupBtn"),
    dinerNameInput: document.getElementById("dinerNameInput"),
    activeSessionCode: document.getElementById("activeSessionCode"),
    copySessionBtn: document.getElementById("copySessionBtn"),
    joinCodeInput: document.getElementById("joinCodeInput"),
    joinSessionBtn: document.getElementById("joinSessionBtn"),
    newSessionBtn: document.getElementById("newSessionBtn"),
    participantsList: document.getElementById("participantsList"),
    quickSessionsList: document.getElementById("quickSessionsList"),
    menuSearchInput: document.getElementById("menuSearchInput"),
    spiceFilterSelect: document.getElementById("spiceFilterSelect"),
    categoryTabs: document.getElementById("categoryTabs"),
    dietButtons: document.querySelectorAll(".filter-chip"),
    menuGrid: document.getElementById("menuGrid"),
    cartCountBadge: document.getElementById("cartCountBadge"),
    cartModeLabel: document.getElementById("cartModeLabel"),
    cartItemsList: document.getElementById("cartItemsList"),
    smartSuggestionsBox: document.getElementById("smartSuggestionsBox"),
    smartSuggestionsList: document.getElementById("smartSuggestionsList"),
    billSummaryBox: document.getElementById("billSummaryBox"),
    billSubtotal: document.getElementById("billSubtotal"),
    billCgst: document.getElementById("billCgst"),
    billSgst: document.getElementById("billSgst"),
    billPkgRow: document.getElementById("billPkgRow"),
    billPkg: document.getElementById("billPkg"),
    billTotal: document.getElementById("billTotal"),
    splitConfigBox: document.getElementById("splitConfigBox"),
    splitPills: document.querySelectorAll(".split-mode-pills .mini-pill"),
    splitEqualControls: document.getElementById("splitEqualControls"),
    equalCountInput: document.getElementById("equalCountInput"),
    equalPreview: document.getElementById("equalPreview"),
    splitItemControls: document.getElementById("splitItemControls"),
    checkoutActions: document.getElementById("checkoutActions"),
    orderNotesInput: document.getElementById("orderNotesInput"),
    placeOrderBtn: document.getElementById("placeOrderBtn"),
    refreshOrdersBtn: document.getElementById("refreshOrdersBtn"),
    customerOrdersList: document.getElementById("customerOrdersList"),
    // Customise modal
    modal: document.getElementById("customiseModal"),
    modalDishName: document.getElementById("modalDishName"),
    modalDishDesc: document.getElementById("modalDishDesc"),
    closeModalBtn: document.getElementById("closeModalBtn"),
    modalQtyMinus: document.getElementById("modalQtyMinus"),
    modalQtyVal: document.getElementById("modalQtyVal"),
    modalQtyPlus: document.getElementById("modalQtyPlus"),
    modalSpiceSelect: document.getElementById("modalSpiceSelect"),
    modalCustomisationsSection: document.getElementById("modalCustomisationsSection"),
    modalCustomisationsList: document.getElementById("modalCustomisationsList"),
    modalSmartAddonsSection: document.getElementById("modalSmartAddonsSection"),
    modalSmartAddonsList: document.getElementById("modalSmartAddonsList"),
    modalNotesInput: document.getElementById("modalNotesInput"),
    modalTotalPreview: document.getElementById("modalTotalPreview"),
    modalAddBtn: document.getElementById("modalAddBtn"),
    // Split existing order modal
    splitModal: document.getElementById("splitOrderModal"),
    splitModalOrderNum: document.getElementById("splitModalOrderNum"),
    closeSplitModalBtn: document.getElementById("closeSplitModalBtn"),
    splitModalBody: document.getElementById("splitModalBody"),
    splitModalTotal: document.getElementById("splitModalTotal"),
    saveSplitModalBtn: document.getElementById("saveSplitModalBtn"),
  };

  let filters = { category: "All", search: "", veg: false, jain: false, vegan: false, spice_level: "All" };
  let splitMode = "none";
  let itemAssignments = {};
  let modalState = { item: null, qty: 1, selectedAddonIds: new Set() };
  let splitModalOrder = null;
  let splitModalMode = "equal";
  let splitModalCount = 2;
  let splitModalAssignments = {};

  function getDinerName() {
    return (els.dinerNameInput.value || "").trim() || "Guest";
  }

  function populateConfigSelectors() {
    els.tableSelect.innerHTML = (state.config.table_numbers || [])
      .map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)
      .join("");
    els.pickupSlotSelect.innerHTML = (state.config.pickup_slots || [])
      .map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`)
      .join("");
    els.modalSpiceSelect.innerHTML = (state.config.spice_preferences || [])
      .map((sp) => `<option value="${escapeHtml(sp)}" ${sp === "Regular" ? "selected" : ""}>${escapeHtml(sp)}</option>`)
      .join("");

    const cats = ["All", ...(state.config.categories || [])];
    els.categoryTabs.innerHTML = cats
      .map((c) => `<button class="cat-tab ${c === filters.category ? "active" : ""}" data-cat="${escapeHtml(c)}">${escapeHtml(c)}</button>`)
      .join("");
  }

  async function loadMenu() {
    const params = new URLSearchParams();
    if (filters.category && filters.category !== "All") params.set("category", filters.category);
    if (filters.search) params.set("search", filters.search);
    if (filters.veg) params.set("veg", "1");
    if (filters.jain) params.set("jain", "1");
    if (filters.vegan) params.set("vegan", "1");
    if (filters.spice_level && filters.spice_level !== "All") params.set("spice_level", filters.spice_level);

    const data = await apiRequest(`/api/menu?${params.toString()}`);
    state.menu = data.items;
    renderMenu();
  }

  async function loadActiveSessions() {
    const data = await apiRequest("/api/sessions");
    state.activeSessions = data.sessions;
    if (!state.session && data.sessions.length > 0) {
      state.session = data.sessions[0];
    } else if (state.session) {
      const updated = data.sessions.find((s) => s.id === state.session.id);
      if (updated) state.session = updated;
    }
    if (!state.session) {
      await startNewSession("dine_in", "T-01");
      return;
    }
    renderSession();
  }

  async function startNewSession(orderMode = "dine_in", tableNumber = "T-01", pickupSlot = null, reuseExisting = false) {
    const data = await apiRequest("/api/sessions", {
      method: "POST",
      body: {
        order_mode: orderMode,
        table_number: tableNumber,
        pickup_slot: pickupSlot,
        participant_name: getDinerName(),
        reuse_existing: reuseExisting,
      },
    });
    state.session = data.session;
    await refreshSessionsListOnly();
    renderSession();
  }

  async function refreshSessionsListOnly() {
    const data = await apiRequest("/api/sessions");
    state.activeSessions = data.sessions;
  }

  async function joinSessionByCode(code) {
    if (!code) return showToast("Enter a session code to join", "error");
    const data = await apiRequest("/api/sessions", {
      method: "POST",
      body: { session_code: code.trim(), participant_name: getDinerName() },
    });
    state.session = data.session;
    els.joinCodeInput.value = "";
    await refreshSessionsListOnly();
    renderSession();
    showToast(`Joined session ${data.session.session_code}`, "success");
  }

  function renderMenu() {
    if (!state.menu.length) {
      els.menuGrid.innerHTML = `<div class="card muted-label">No dishes match your search/dietary filters.</div>`;
      return;
    }

    els.menuGrid.innerHTML = state.menu
      .map((item) => {
        const vegBadge = item.is_veg
          ? `<span class="badge badge-veg">🟢 Veg</span>`
          : `<span class="badge badge-nonveg">🔴 Non-Veg</span>`;
        const jainBadge = item.is_jain ? `<span class="badge badge-jain">🙏 Jain</span>` : "";
        const veganBadge = item.is_vegan ? `<span class="badge badge-vegan">🌱 Vegan</span>` : "";
        const spiceBadge = item.spice_level !== "None" ? `<span class="badge badge-spice">🌶️ ${escapeHtml(item.spice_level)}</span>` : "";
        const stockText = !item.in_stock || item.stock_count <= 0
          ? `<span class="badge badge-nonveg">Out of Stock</span>`
          : `<span class="muted-label">⏱️ ${item.prep_time_mins}m</span>`;

        return `
          <article class="menu-card ${!item.in_stock ? "out-of-stock" : ""}">
            <div>
              <div class="menu-top">
                <div class="diet-badges">${vegBadge}${jainBadge}${veganBadge}${spiceBadge}</div>
                <span class="menu-emoji">${escapeHtml(item.image_emoji)}</span>
              </div>
              <h3 class="menu-title">${escapeHtml(item.name)}</h3>
              <p class="menu-desc">${escapeHtml(item.description)}</p>
            </div>
            <div class="menu-footer">
              <div>
                <div class="price-tag">${formatINR(item.price_paise)}</div>
                ${stockText}
              </div>
              <button class="btn btn-primary btn-sm open-customise-btn" data-id="${item.id}" ${!item.in_stock ? "disabled" : ""}>
                ${item.in_stock ? "+ Customise & Add" : "Unavailable"}
              </button>
            </div>
          </article>
        `;
      })
      .join("");
  }

  function renderSession() {
    const sess = state.session;
    if (!sess) return;

    const isDineIn = sess.order_mode === "dine_in";
    els.modeDineInBtn.classList.toggle("active", isDineIn);
    els.modeTakeawayBtn.classList.toggle("active", !isDineIn);
    els.dineInControls.classList.toggle("hidden", !isDineIn);
    els.takeawayControls.classList.toggle("hidden", isDineIn);

    if (isDineIn && sess.table_number) {
      const optExists = Array.from(els.tableSelect.options).some((o) => o.value === sess.table_number);
      if (optExists) {
        els.tableSelect.value = sess.table_number;
        els.customTableInput.value = "";
      } else {
        els.customTableInput.value = sess.table_number;
      }
    }
    if (!isDineIn && sess.pickup_slot) {
      els.pickupSlotSelect.value = sess.pickup_slot;
    }

    els.activeSessionCode.textContent = sess.session_code;
    els.cartModeLabel.textContent = isDineIn ? `🪑 Table ${sess.table_number}` : `🛍️ Takeaway (${sess.pickup_slot})`;
    els.cartCountBadge.textContent = String(sess.item_count || 0);

    els.participantsList.innerHTML =
      `<span class="muted-label">Diners at table:</span>` +
      sess.participants.map((p) => `<span class="chip">👤 ${escapeHtml(p)}</span>`).join("");

    const otherSessions = (state.activeSessions || []).filter((s) => s.id !== sess.id).slice(0, 4);
    els.quickSessionsList.innerHTML = otherSessions.length
      ? `<span class="muted-label">Active tables:</span>` +
        otherSessions
          .map(
            (s) =>
              `<button class="quick-join-btn" data-code="${escapeHtml(s.session_code)}">Join ${escapeHtml(s.session_code)} (${s.item_count})</button>`
          )
          .join("")
      : "";

    renderCart(sess);
  }

  function renderCart(sess) {
    const items = sess.cart_items || [];
    if (!items.length) {
      els.cartItemsList.innerHTML = `<p class="muted-label">Your shared cart is empty. Add dishes from the menu or join a table code!</p>`;
      els.smartSuggestionsBox.classList.add("hidden");
      els.billSummaryBox.classList.add("hidden");
      els.splitConfigBox.classList.add("hidden");
      els.checkoutActions.classList.add("hidden");
      return;
    }

    els.cartItemsList.innerHTML = items
      .map((ci) => {
        const addonText = ci.selected_addons.length
          ? `+ ${ci.selected_addons.map((a) => escapeHtml(a.name)).join(", ")}`
          : "";
        return `
          <div class="cart-item">
            <div class="cart-item-top">
              <span>${escapeHtml(ci.image_emoji)} ${escapeHtml(ci.item_name)}</span>
              <span>${formatINR(ci.line_total_paise)}</span>
            </div>
            <div class="cart-item-meta">
              Added by <strong>${escapeHtml(ci.added_by)}</strong> • Spice: ${escapeHtml(ci.spice_preference)}
              ${addonText ? `<br>${addonText}` : ""}
              ${ci.notes ? `<br>📝 "${escapeHtml(ci.notes)}"` : ""}
            </div>
            <div class="cart-item-bottom">
              <div class="qty-stepper">
                <button class="cart-qty-btn" data-cid="${ci.id}" data-qty="${ci.quantity - 1}">−</button>
                <span>${ci.quantity}</span>
                <button class="cart-qty-btn" data-cid="${ci.id}" data-qty="${ci.quantity + 1}">+</button>
              </div>
              <button class="btn btn-ghost btn-sm cart-remove-btn" data-cid="${ci.id}">Remove</button>
            </div>
          </div>
        `;
      })
      .join("");

    // Smart suggestions
    const suggestions = sess.smart_suggestions || [];
    if (suggestions.length) {
      els.smartSuggestionsBox.classList.remove("hidden");
      els.smartSuggestionsList.innerHTML = suggestions
        .map(
          (s) => `
          <div class="smart-item">
            <div>
              <strong>${escapeHtml(s.image_emoji)} ${escapeHtml(s.name)}</strong>
              <span class="muted-label"> • ${formatINR(s.price_paise)}</span>
            </div>
            <button class="btn btn-secondary btn-sm quick-add-btn" data-mid="${s.id}">+ Add</button>
          </div>`
        )
        .join("");
    } else {
      els.smartSuggestionsBox.classList.add("hidden");
    }

    // Bill breakdown
    const bill = sess.bill;
    els.billSummaryBox.classList.remove("hidden");
    els.billSubtotal.textContent = formatINR(bill.subtotal_paise);
    els.billCgst.textContent = formatINR(bill.cgst_paise);
    els.billSgst.textContent = formatINR(bill.sgst_paise);
    els.billPkgRow.classList.toggle("hidden", bill.packaging_fee_paise <= 0);
    els.billPkg.textContent = formatINR(bill.packaging_fee_paise);
    els.billTotal.textContent = formatINR(bill.total_paise);

    // Split bill UI
    els.splitConfigBox.classList.remove("hidden");
    els.checkoutActions.classList.remove("hidden");
    renderSplitPreview(sess);
  }

  function renderSplitPreview(sess) {
    els.splitEqualControls.classList.toggle("hidden", splitMode !== "equal");
    els.splitItemControls.classList.toggle("hidden", splitMode !== "item_wise");

    if (splitMode === "equal") {
      const n = Math.max(2, Math.min(20, parseInt(els.equalCountInput.value || "2", 10)));
      const perPerson = Math.ceil(sess.bill.total_paise / n);
      els.equalPreview.textContent = `≈ ${formatINR(perPerson)} / person`;
    } else if (splitMode === "item_wise") {
      const diners = Array.from(new Set([...sess.participants, getDinerName()]));
      els.splitItemControls.innerHTML = sess.cart_items
        .map((ci) => {
          const currentOwner = itemAssignments[ci.id] || ci.added_by;
          itemAssignments[ci.id] = currentOwner;
          const options = Array.from(new Set([...diners, currentOwner]))
            .map((d) => `<option value="${escapeHtml(d)}" ${d === currentOwner ? "selected" : ""}>${escapeHtml(d)}</option>`)
            .join("");
          return `
            <div class="split-assign-row">
              <span>${escapeHtml(ci.item_name)} × ${ci.quantity} (${formatINR(ci.line_total_paise)})</span>
              <select class="split-owner-select" data-cid="${ci.id}">${options}</select>
            </div>
          `;
        })
        .join("");
    }
  }

  function openCustomiseModal(itemId) {
    const item = state.menu.find((m) => m.id === itemId);
    if (!item) return;
    modalState = { item, qty: 1, selectedAddonIds: new Set() };
    els.modalDishName.textContent = `${item.image_emoji} ${item.name}`;
    els.modalDishDesc.textContent = item.description;
    els.modalQtyVal.textContent = "1";
    els.modalNotesInput.value = "";
    els.modalSpiceSelect.value = item.is_jain ? "No Spice / Jain" : "Regular";

    const customisations = item.addons.filter((a) => a.category === "customisation");
    const smartAddons = item.addons.filter((a) => a.category === "smart_addon");

    els.modalCustomisationsSection.classList.toggle("hidden", !customisations.length);
    els.modalSmartAddonsSection.classList.toggle("hidden", !smartAddons.length);

    const renderAddonList = (list) =>
      list
        .map(
          (a) => `
          <label class="addon-option">
            <span><input type="checkbox" class="addon-check" value="${a.id}" /> ${escapeHtml(a.name)}</span>
            <span>${a.price_paise > 0 ? `+${formatINR(a.price_paise)}` : "Free"}</span>
          </label>`
        )
        .join("");

    els.modalCustomisationsList.innerHTML = renderAddonList(customisations);
    els.modalSmartAddonsList.innerHTML = renderAddonList(smartAddons);
    updateModalPrice();
    els.modal.classList.remove("hidden");
  }

  function updateModalPrice() {
    if (!modalState.item) return;
    let addonsTotal = 0;
    for (const a of modalState.item.addons) {
      if (modalState.selectedAddonIds.has(a.id)) addonsTotal += a.price_paise;
    }
    const total = (modalState.item.price_paise + addonsTotal) * modalState.qty;
    els.modalTotalPreview.textContent = formatINR(total);
  }

  function renderCustomerOrders() {
    const orders = (state.orders || []).slice(0, 8);
    if (!orders.length) {
      els.customerOrdersList.innerHTML = `<p class="muted-label">No orders placed yet.</p>`;
      return;
    }

    const steps = ["Queued", "Preparing", "Ready", "Served"];
    els.customerOrdersList.innerHTML = orders
      .map((o) => {
        const curIdx = steps.indexOf(o.status);
        const stepper =
          o.status === "Cancelled"
            ? `<div class="badge badge-nonveg">Cancelled</div>`
            : `<div class="status-stepper">
                ${steps
                  .map((st, idx) => {
                    const cls = idx < curIdx ? "done" : idx === curIdx ? "current" : "";
                    return `<div class="step-pill ${cls}">${st}</div>`;
                  })
                  .join("")}
              </div>`;

        const whereLabel = o.order_mode === "dine_in" ? `🪑 Table ${escapeHtml(o.table_number)}` : `🛍️ Pickup: ${escapeHtml(o.pickup_slot)}`;
        const sharesHtml = o.split_shares.length
          ? `<div style="margin-top:0.45rem;">
              ${o.split_shares
                .map(
                  (s) => `
                  <div class="share-row">
                    <span>${escapeHtml(s.participant_name)} — <strong>${formatINR(s.amount_paise)}</strong></span>
                    <button class="btn btn-sm ${s.is_paid ? "btn-secondary" : "btn-primary"} toggle-share-btn"
                      data-oid="${o.id}" data-sid="${s.id}" data-paid="${s.is_paid ? "0" : "1"}">
                      ${s.is_paid ? "✓ Paid" : "Mark Paid"}
                    </button>
                  </div>`
                )
                .join("")}
            </div>`
          : "";

        return `
          <div class="tracker-order">
            <div class="tracker-head">
              <strong>${escapeHtml(o.order_number)} • ${formatINR(o.total_paise)}</strong>
              <span class="muted-label">${whereLabel}</span>
            </div>
            <div class="muted-label">${o.items.map((i) => `${i.quantity}× ${escapeHtml(i.item_name)}`).join(", ")}</div>
            ${stepper}
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.35rem;">
              <span class="muted-label">GST incl. ${formatINR(o.gst_total_paise)}</span>
              <button class="btn btn-ghost btn-sm open-split-modal-btn" data-oid="${o.id}">💸 Split / Edit Split</button>
            </div>
            ${sharesHtml}
          </div>
        `;
      })
      .join("");
  }

  function openSplitOrderModal(orderId) {
    const order = state.orders.find((o) => o.id === orderId);
    if (!order) return;
    splitModalOrder = order;
    splitModalMode = order.split_mode === "item_wise" ? "item_wise" : "equal";
    splitModalCount = Math.max(2, order.split_shares.length || 2);
    splitModalAssignments = {};
    for (const item of order.items) {
      splitModalAssignments[item.id] = item.added_by || order.customer_name;
    }
    els.splitModalOrderNum.textContent = order.order_number;
    els.splitModalTotal.textContent = formatINR(order.total_paise);
    renderSplitOrderModalBody();
    els.splitModal.classList.remove("hidden");
  }

  function renderSplitOrderModalBody() {
    if (!splitModalOrder) return;
    const diners = Array.from(new Set(splitModalOrder.items.map((i) => i.added_by).concat([getDinerName()])));
    const equalPer = Math.ceil(splitModalOrder.total_paise / splitModalCount);

    els.splitModalBody.innerHTML = `
      <div class="split-mode-pills">
        <button class="mini-pill ${splitModalMode === "equal" ? "active" : ""}" data-msplit="equal">Equal Split</button>
        <button class="mini-pill ${splitModalMode === "item_wise" ? "active" : ""}" data-msplit="item_wise">Item-Wise Split</button>
      </div>
      ${
        splitModalMode === "equal"
          ? `<div class="inline-group">
              <label>Number of people</label>
              <input id="modalEqualCount" type="number" min="2" max="20" value="${splitModalCount}" class="input-xs" />
              <span class="muted-label">≈ ${formatINR(equalPer)} each</span>
            </div>`
          : `<div class="addons-list">
              ${splitModalOrder.items
                .map(
                  (it) => `
                  <div class="split-assign-row">
                    <span>${escapeHtml(it.item_name)} × ${it.quantity} (${formatINR(it.line_total_paise)})</span>
                    <select class="modal-item-owner" data-iid="${it.id}">
                      ${diners
                        .map((d) => `<option value="${escapeHtml(d)}" ${splitModalAssignments[it.id] === d ? "selected" : ""}>${escapeHtml(d)}</option>`)
                        .join("")}
                    </select>
                  </div>`
                )
                .join("")}
            </div>`
      }
    `;
  }

  // Event listeners
  function bindEvents() {
    els.categoryTabs.addEventListener("click", (e) => {
      const btn = e.target.closest(".cat-tab");
      if (!btn) return;
      filters.category = btn.dataset.cat;
      els.categoryTabs.querySelectorAll(".cat-tab").forEach((b) => b.classList.toggle("active", b === btn));
      loadMenu().catch((err) => showToast(err.message, "error"));
    });

    els.menuSearchInput.addEventListener("input", () => {
      filters.search = els.menuSearchInput.value;
      loadMenu().catch((err) => showToast(err.message, "error"));
    });

    els.spiceFilterSelect.addEventListener("change", () => {
      filters.spice_level = els.spiceFilterSelect.value;
      loadMenu().catch((err) => showToast(err.message, "error"));
    });

    els.dietButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.diet;
        filters[key] = !filters[key];
        btn.classList.toggle("active", filters[key]);
        loadMenu().catch((err) => showToast(err.message, "error"));
      });
    });

    els.modeDineInBtn.addEventListener("click", async () => {
      if (!state.session) return;
      const tbl = (els.customTableInput.value || els.tableSelect.value || "T-01").trim();
      const data = await apiRequest(`/api/sessions/${state.session.id}/mode`, {
        method: "PATCH",
        body: { order_mode: "dine_in", table_number: tbl },
      });
      state.session = data.session;
      renderSession();
    });

    els.modeTakeawayBtn.addEventListener("click", async () => {
      if (!state.session) return;
      const slot = els.pickupSlotSelect.value;
      const data = await apiRequest(`/api/sessions/${state.session.id}/mode`, {
        method: "PATCH",
        body: { order_mode: "takeaway", pickup_slot: slot },
      });
      state.session = data.session;
      renderSession();
    });

    els.applyModeBtn.addEventListener("click", async () => {
      if (!state.session) return;
      const tbl = (els.customTableInput.value || els.tableSelect.value || "T-01").trim();
      try {
        const data = await apiRequest(`/api/sessions/${state.session.id}/mode`, {
          method: "PATCH",
          body: { order_mode: "dine_in", table_number: tbl },
        });
        state.session = data.session;
        renderSession();
        showToast(`Table set to ${data.session.table_number}`, "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    els.applyPickupBtn.addEventListener("click", async () => {
      if (!state.session) return;
      try {
        const data = await apiRequest(`/api/sessions/${state.session.id}/mode`, {
          method: "PATCH",
          body: { order_mode: "takeaway", pickup_slot: els.pickupSlotSelect.value },
        });
        state.session = data.session;
        renderSession();
        showToast(`Pickup slot set: ${data.session.pickup_slot}`, "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    els.copySessionBtn.addEventListener("click", () => {
      const code = state.session?.session_code;
      if (!code) return;
      navigator.clipboard?.writeText(code).catch(() => {});
      showToast(`Copied session code ${code}`, "success");
    });

    els.joinSessionBtn.addEventListener("click", () => {
      joinSessionByCode(els.joinCodeInput.value).catch((err) => showToast(err.message, "error"));
    });

    els.newSessionBtn.addEventListener("click", () => {
      const tbl = (els.customTableInput.value || els.tableSelect.value || "T-05").trim();
      startNewSession("dine_in", tbl, null, false)
        .then(() => showToast(`Started fresh session ${state.session.session_code}`, "success"))
        .catch((err) => showToast(err.message, "error"));
    });

    els.quickSessionsList.addEventListener("click", (e) => {
      const btn = e.target.closest(".quick-join-btn");
      if (btn) joinSessionByCode(btn.dataset.code).catch((err) => showToast(err.message, "error"));
    });

    els.menuGrid.addEventListener("click", (e) => {
      const btn = e.target.closest(".open-customise-btn");
      if (btn) openCustomiseModal(Number(btn.dataset.id));
    });

    // Modal controls
    els.closeModalBtn.addEventListener("click", () => els.modal.classList.add("hidden"));
    els.modalQtyMinus.addEventListener("click", () => {
      modalState.qty = Math.max(1, modalState.qty - 1);
      els.modalQtyVal.textContent = String(modalState.qty);
      updateModalPrice();
    });
    els.modalQtyPlus.addEventListener("click", () => {
      modalState.qty = Math.min(20, modalState.qty + 1);
      els.modalQtyVal.textContent = String(modalState.qty);
      updateModalPrice();
    });
    els.modal.addEventListener("change", (e) => {
      if (e.target.classList.contains("addon-check")) {
        const id = Number(e.target.value);
        if (e.target.checked) modalState.selectedAddonIds.add(id);
        else modalState.selectedAddonIds.delete(id);
        updateModalPrice();
      }
    });
    els.modalAddBtn.addEventListener("click", async () => {
      if (!modalState.item || !state.session) return;
      try {
        const data = await apiRequest(`/api/sessions/${state.session.id}/cart`, {
          method: "POST",
          body: {
            menu_item_id: modalState.item.id,
            quantity: modalState.qty,
            added_by: getDinerName(),
            spice_preference: els.modalSpiceSelect.value,
            addon_ids: Array.from(modalState.selectedAddonIds),
            notes: els.modalNotesInput.value,
          },
        });
        state.session = data.session;
        els.modal.classList.add("hidden");
        renderSession();
        showToast(`Added ${modalState.item.name} to shared cart`, "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    // Cart controls
    els.cartItemsList.addEventListener("click", async (e) => {
      const qtyBtn = e.target.closest(".cart-qty-btn");
      const remBtn = e.target.closest(".cart-remove-btn");
      if (!state.session) return;
      try {
        if (qtyBtn) {
          const data = await apiRequest(`/api/sessions/${state.session.id}/cart/${qtyBtn.dataset.cid}`, {
            method: "PATCH",
            body: { quantity: Number(qtyBtn.dataset.qty) },
          });
          state.session = data.session;
          renderSession();
        } else if (remBtn) {
          const data = await apiRequest(`/api/sessions/${state.session.id}/cart/${remBtn.dataset.cid}`, {
            method: "DELETE",
          });
          state.session = data.session;
          renderSession();
        }
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    els.smartSuggestionsList.addEventListener("click", async (e) => {
      const btn = e.target.closest(".quick-add-btn");
      if (!btn || !state.session) return;
      try {
        const data = await apiRequest(`/api/sessions/${state.session.id}/cart`, {
          method: "POST",
          body: { menu_item_id: Number(btn.dataset.mid), quantity: 1, added_by: getDinerName(), spice_preference: "Regular" },
        });
        state.session = data.session;
        renderSession();
        showToast("Smart pairing added to cart!", "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    els.splitPills.forEach((pill) => {
      pill.addEventListener("click", () => {
        splitMode = pill.dataset.split;
        els.splitPills.forEach((p) => p.classList.toggle("active", p === pill));
        if (state.session) renderSplitPreview(state.session);
      });
    });

    els.equalCountInput.addEventListener("input", () => {
      if (state.session) renderSplitPreview(state.session);
    });

    els.splitItemControls.addEventListener("change", (e) => {
      const sel = e.target.closest(".split-owner-select");
      if (sel) itemAssignments[sel.dataset.cid] = sel.value;
    });

    els.placeOrderBtn.addEventListener("click", async () => {
      if (!state.session) return;
      let splitConfig = null;
      if (splitMode === "equal") {
        const count = Math.max(2, parseInt(els.equalCountInput.value || "2", 10));
        const baseNames = Array.from(new Set([...state.session.participants, getDinerName()]));
        const participants = Array.from({ length: count }, (_, idx) => baseNames[idx] || `Diner ${idx + 1}`);
        splitConfig = { split_count: count, participants };
      } else if (splitMode === "item_wise") {
        splitConfig = { assignments: itemAssignments };
      }

      try {
        const data = await apiRequest(`/api/sessions/${state.session.id}/checkout`, {
          method: "POST",
          body: {
            customer_name: getDinerName(),
            split_mode: splitMode,
            split_config: splitConfig,
            special_instructions: els.orderNotesInput.value,
          },
        });
        els.orderNotesInput.value = "";
        splitMode = "none";
        els.splitPills.forEach((p) => p.classList.toggle("active", p.dataset.split === "none"));
        showToast(`Order ${data.order.order_number} sent to Kitchen!`, "success");
        // Start a fresh active session for the same table/mode for next round
        await startNewSession(data.order.order_mode, data.order.table_number || "T-01", data.order.pickup_slot, false);
        await refreshAllOrders();
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    els.refreshOrdersBtn.addEventListener("click", () => refreshAllOrders());

    els.customerOrdersList.addEventListener("click", async (e) => {
      const shareBtn = e.target.closest(".toggle-share-btn");
      const splitBtn = e.target.closest(".open-split-modal-btn");
      if (shareBtn) {
        try {
          await apiRequest(`/api/orders/${shareBtn.dataset.oid}/shares/${shareBtn.dataset.sid}`, {
            method: "PATCH",
            body: { is_paid: shareBtn.dataset.paid === "1" },
          });
          await refreshAllOrders();
        } catch (err) {
          showToast(err.message, "error");
        }
      } else if (splitBtn) {
        openSplitOrderModal(Number(splitBtn.dataset.oid));
      }
    });

    // Split Existing Order Modal events
    els.closeSplitModalBtn.addEventListener("click", () => els.splitModal.classList.add("hidden"));
    els.splitModalBody.addEventListener("click", (e) => {
      const pill = e.target.closest("[data-msplit]");
      if (pill) {
        splitModalMode = pill.dataset.msplit;
        renderSplitOrderModalBody();
      }
    });
    els.splitModalBody.addEventListener("input", (e) => {
      if (e.target.id === "modalEqualCount") {
        splitModalCount = Math.max(2, Math.min(20, parseInt(e.target.value || "2", 10)));
        renderSplitOrderModalBody();
      }
    });
    els.splitModalBody.addEventListener("change", (e) => {
      if (e.target.classList.contains("modal-item-owner")) {
        splitModalAssignments[e.target.dataset.iid] = e.target.value;
      }
    });
    els.saveSplitModalBtn.addEventListener("click", async () => {
      if (!splitModalOrder) return;
      const splitConfig =
        splitModalMode === "equal"
          ? { split_count: splitModalCount }
          : { assignments: splitModalAssignments };
      try {
        await apiRequest(`/api/orders/${splitModalOrder.id}/split`, {
          method: "POST",
          body: { split_mode: splitModalMode, split_config: splitConfig },
        });
        els.splitModal.classList.add("hidden");
        await refreshAllOrders();
        showToast("Bill split updated", "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  }

  bindEvents();

  return {
    init: async () => {
      populateConfigSelectors();
      await Promise.all([loadMenu(), loadActiveSessions()]);
    },
    loadMenu,
    loadActiveSessions,
    renderSession,
    renderCustomerOrders,
  };
}
