// Forex Analysis System — Web Interface
// Talks ONLY to the Backend API (never to MT5 directly). The user never
// selects a timeframe — the backend decides HTF/MTF/LTF internally.

const DEFAULT_API_BASE_URL = "http://localhost:8000";

function getApiBaseUrl() {
  return localStorage.getItem("apiBaseUrl") || DEFAULT_API_BASE_URL;
}

async function api(path, options) {
  const res = await fetch(getApiBaseUrl() + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function el(id) { return document.getElementById(id); }

function setupSettingsPanel() {
  el("apiBaseUrl").value = getApiBaseUrl();
  el("settingsToggle").addEventListener("click", () => {
    el("settingsPanel").classList.toggle("hidden");
  });
  el("saveSettings").addEventListener("click", () => {
    const value = el("apiBaseUrl").value.trim();
    if (value) {
      localStorage.setItem("apiBaseUrl", value.replace(/\/$/, ""));
      el("settingsPanel").classList.add("hidden");
      loadFormOptions();
    }
  });
}

function populateSelectWithPresets(selectEl, presets, allowCustom, customInputEl) {
  selectEl.innerHTML = "";
  for (const value of presets) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    selectEl.appendChild(opt);
  }
  if (allowCustom) {
    const opt = document.createElement("option");
    opt.value = "custom";
    opt.textContent = "Custom…";
    selectEl.appendChild(opt);
  }
  selectEl.addEventListener("change", () => {
    customInputEl.classList.toggle("hidden", selectEl.value !== "custom");
  });
}

async function loadFormOptions() {
  const resultPanel = el("resultPanel");
  try {
    const [symbolsResp, riskConfig, lotConfig] = await Promise.all([
      api("/market-data/symbols"),
      api("/config/risk"),
      api("/config/lots"),
    ]);

    const symbolSelect = el("symbol");
    symbolSelect.innerHTML = "";
    for (const s of symbolsResp.symbols) {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      symbolSelect.appendChild(opt);
    }

    populateSelectWithPresets(el("riskPercent"), riskConfig.presets_percent, riskConfig.allow_custom_risk_percent, el("riskPercentCustom"));
    populateSelectWithPresets(el("lotSize"), lotConfig.presets, lotConfig.allow_custom_lot, el("lotSizeCustom"));

    el("analyzeButton").disabled = false;
  } catch (err) {
    resultPanel.innerHTML = `<div class="error-notice">Could not reach the Backend API at ${getApiBaseUrl()}. Open Settings (⚙) and check the URL. (${err.message})</div>`;
  }
}

function setupLotModeToggle() {
  const radios = document.querySelectorAll('input[name="lotMode"]');
  const lotSelect = el("lotSize");
  const lotCustom = el("lotSizeCustom");
  const update = () => {
    const manual = document.querySelector('input[name="lotMode"]:checked').value === "MANUAL";
    lotSelect.classList.toggle("hidden", !manual);
    lotCustom.classList.toggle("hidden", !manual || lotSelect.value !== "custom");
  };
  radios.forEach((r) => r.addEventListener("change", update));
  update();
}

function readNumberOrSelect(selectEl, customEl) {
  if (selectEl.value === "custom") {
    return customEl.value ? Number(customEl.value) : null;
  }
  return Number(selectEl.value);
}

async function runAnalysis() {
  const button = el("analyzeButton");
  const resultPanel = el("resultPanel");
  button.disabled = true;
  resultPanel.innerHTML = `<p class="placeholder">Analyzing…</p>`;

  const lotMode = document.querySelector('input[name="lotMode"]:checked').value;
  const capitalRaw = el("capital").value;

  const payload = {
    symbol: el("symbol").value,
    risk_percent: readNumberOrSelect(el("riskPercent"), el("riskPercentCustom")),
    capital: capitalRaw ? Number(capitalRaw) : null,
    lot_mode: lotMode,
    lot_size: lotMode === "MANUAL" ? readNumberOrSelect(el("lotSize"), el("lotSizeCustom")) : null,
  };

  try {
    const data = await api("/analyze", { method: "POST", body: JSON.stringify(payload) });
    renderResult(data);
  } catch (err) {
    resultPanel.innerHTML = `<div class="error-notice">${err.message}</div>`;
  } finally {
    button.disabled = false;
  }
}

function fmt(value, digits = 5) {
  return value === null || value === undefined ? "N/A" : Number(value).toFixed(digits);
}

function fmtMoney(value) {
  return value === null || value === undefined ? "N/A" : `$${Number(value).toFixed(2)}`;
}

function renderResult(data) {
  const resultPanel = el("resultPanel");

  if (data.status === "NO_SETUP_FOUND") {
    resultPanel.innerHTML = `<div class="notice">No qualifying trade setup found for ${data.symbol} right now. No levels are shown — this system never displays a signal it doesn't have.</div>`;
    return;
  }
  if (data.status === "REJECTED_MIN_RISK_REWARD") {
    resultPanel.innerHTML = `<div class="notice">A potential setup was found for ${data.symbol}, but its Risk:Reward (1:${fmt(data.risk_reward_tp1, 2)}) is below the minimum allowed (1:${data.min_risk_reward}). No signal is shown — TP is never adjusted just to force a ratio.</div>`;
    return;
  }

  const directionClass = data.direction === "BUY" ? "buy" : "sell";
  const labelClass = data.confidence_label.toLowerCase();
  const statusClass = data.status === "ACTIVE" ? "active" : "expired";
  const reasonsHtml = (data.confidence_reasons || []).map((r) => `<li>${r}</li>`).join("");
  const financialNote = data.financial_disclaimer
    ? `<div class="notice full-row">${data.financial_disclaimer}</div>` : "";

  resultPanel.innerHTML = `
    <div class="result-header">
      <span class="badge ${directionClass}">${data.direction}</span>
      <span class="badge ${labelClass}">${data.confidence_label} (${data.confidence_score}/100)</span>
      <span class="badge ${statusClass}">${data.status}</span>
    </div>
    <div class="result-grid">
      <div><div class="label">Selected Strategy</div><div class="value">${data.selected_strategy}</div></div>
      <div><div class="label">Timeframe Used (H/M/E)</div><div class="value">${data.timeframe_used.higher} / ${data.timeframe_used.middle} / ${data.timeframe_used.entry}</div></div>

      <div><div class="label">Agreeing Strategies</div><div class="value">${(data.agreeing_strategies || []).join(", ") || "—"}</div></div>
      <div><div class="label">Conflicting Strategies</div><div class="value">${(data.conflicting_strategies || []).join(", ") || "—"}</div></div>

      <div><div class="label">Entry</div><div class="value">${fmt(data.entry)}</div></div>
      <div><div class="label">Stop Loss</div><div class="value">${fmt(data.stop_loss)}</div></div>

      <div><div class="label">TP1</div><div class="value">${fmt(data.take_profit_1)}</div></div>
      <div><div class="label">TP2</div><div class="value">${fmt(data.take_profit_2)}</div></div>

      <div><div class="label">R:R to TP1</div><div class="value">1:${fmt(data.risk_reward_tp1, 2)}</div></div>
      <div><div class="label">R:R to TP2</div><div class="value">1:${fmt(data.risk_reward_tp2, 2)}</div></div>

      <div><div class="label">Lot Size (${data.lot_source})</div><div class="value">${data.lot_size ?? "N/A"}</div></div>
      <div><div class="label">Risk Amount</div><div class="value">${fmtMoney(data.risk_amount)}</div></div>

      <div><div class="label">Expected Profit TP1</div><div class="value">${fmtMoney(data.expected_profit_tp1)}</div></div>
      <div><div class="label">Expected Profit TP2</div><div class="value">${fmtMoney(data.expected_profit_tp2)}</div></div>

      <div><div class="label">Expected Loss</div><div class="value">${fmtMoney(data.expected_loss)}</div></div>
      <div><div class="label">Spread</div><div class="value">${fmt(data.spread)}</div></div>

      ${financialNote}

      <div class="full-row"><div class="label">Confidence Reasons</div><ul class="reasons-list">${reasonsHtml}</ul></div>

      <div><div class="label">Analysis Time</div><div class="value">${new Date(data.analysis_timestamp).toLocaleString()}</div></div>
      <div><div class="label">Valid Until</div><div class="value">${new Date(data.valid_until).toLocaleString()}</div></div>
    </div>
  `;
}

document.addEventListener("DOMContentLoaded", () => {
  setupSettingsPanel();
  setupLotModeToggle();
  el("analyzeButton").disabled = true;
  el("analyzeButton").addEventListener("click", runAnalysis);
  loadFormOptions();
});
