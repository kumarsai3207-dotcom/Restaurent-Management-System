/**
 * Application bootstrap: shared state, role navigation, toast notifications, and SSE sync.
 */

import { RealtimeClient, apiRequest } from "/js/api.js";
import { createCustomerController } from "/js/customer.js";
import { createKdsController } from "/js/kds.js";
import { createAdminController } from "/js/admin.js";

const portalParam = new URLSearchParams(window.location.search).get("portal") || "customer";

const initialView = portalParam === "admin" ? "admin" : portalParam === "kds" ? "kds" : "customer";

const state = {
  config: {},
  menu: [],
  session: null,
  activeSessions: [],
  orders: [],
  activeView: initialView,
};

const toastContainer = document.getElementById("toastContainer");
const realtimeBadge = document.getElementById("realtimeBadge");
const roleTabs = document.querySelectorAll(".role-tab");

roleTabs.forEach((tab) => {
  if (tab.dataset.view !== initialView) tab.hidden = true;
});

const viewSections = {
  customer: document.getElementById("view-customer"),
  kds: document.getElementById("view-kds"),
  admin: document.getElementById("view-admin"),
};

function showToast(message, variant = "info") {
  const el = document.createElement("div");
  el.className = `toast ${variant}`;
  el.textContent = message;
  toastContainer.appendChild(el);
  window.setTimeout(() => el.remove(), 3500);
}

let customerCtrl;
let kdsCtrl;
let adminCtrl;

async function refreshAllOrders() {
  const data = await apiRequest("/api/orders");
  state.orders = data.orders;
  customerCtrl.renderCustomerOrders();
  kdsCtrl.render();
  if (state.activeView === "admin") {
    adminCtrl.refreshAdminData().catch(() => {});
  }
}

function switchView(viewName) {
  state.activeView = viewName;
  roleTabs.forEach((t) => t.classList.toggle("active", t.dataset.view === viewName));
  Object.entries(viewSections).forEach(([k, sec]) => sec.classList.toggle("active", k === viewName));
  if (viewName === "admin") {
    adminCtrl.refreshAdminData().catch((err) => showToast(err.message, "error"));
  } else if (viewName === "kds") {
    refreshAllOrders().catch(() => {});
  }
}

roleTabs.forEach((tab) => {
  tab.addEventListener("click", () => switchView(tab.dataset.view));
});

async function bootstrap() {
  try {
    state.config = await apiRequest("/api/health");
    customerCtrl = createCustomerController(state, showToast, refreshAllOrders);
    kdsCtrl = createKdsController(state, showToast, refreshAllOrders);
    adminCtrl = createAdminController(state, showToast, () => customerCtrl.loadMenu());

    await Promise.all([customerCtrl.init(), refreshAllOrders()]);
    switchView(initialView);

    const rt = new RealtimeClient(
      async (evtName, payload) => {
        if (evtName === "session.updated" && payload?.id) {
          if (state.session && payload.id === state.session.id) {
            state.session = payload;
            customerCtrl.renderSession();
          }
          await customerCtrl.loadActiveSessions();
        } else if (evtName === "order.created") {
          showToast(`New Kitchen Ticket: ${payload.order_number}`, "info");
          await refreshAllOrders();
        } else if (evtName === "order.updated") {
          await refreshAllOrders();
        } else if (evtName === "menu.updated") {
          await customerCtrl.loadMenu();
          if (state.activeView === "admin") await adminCtrl.refreshAdminData();
        } else if (evtName === "poll.tick") {
          await refreshAllOrders();
          if (state.session) {
            const sRes = await apiRequest(`/api/sessions/${state.session.id}`).catch(() => null);
            if (sRes?.session && sRes.session.status === "active") {
              state.session = sRes.session;
              customerCtrl.renderSession();
            }
          }
        }
      },
      (status) => {
        if (status === "live") {
          realtimeBadge.className = "sync-badge live";
          realtimeBadge.textContent = "● Live SSE Sync";
        } else {
          realtimeBadge.className = "sync-badge polling";
          realtimeBadge.textContent = "● Auto-Sync (Polling)";
        }
      }
    );
    rt.start();
  } catch (err) {
    showToast(`Startup error: ${err.message}`, "error");
  }
}

bootstrap();
