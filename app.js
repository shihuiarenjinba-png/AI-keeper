const STORAGE_KEY = "ai-keeper-config";
const TOKEN_KEY = "ai-keeper-token";
const DATA_PATHS = {
  accounts: "data/accounts.json",
  events: "data/events.json",
  settings: "data/settings.json",
};
const DEFAULT_SETTINGS = {
  services: ["Codex", "ChatGPT", "Claude", "Cursor", "Gemini"].map((name) => ({
    name,
    defaultLimitDurationDays: 7,
  })),
};

const state = {
  view: "dashboard",
  config: loadConfig(),
  token: localStorage.getItem(TOKEN_KEY) || "",
  accounts: [],
  events: [],
  settings: DEFAULT_SETTINGS,
  shas: {},
  filters: { accounts: "", status: "all", events: "" },
};

const $ = (selector) => document.querySelector(selector);
const els = {
  viewTitle: $("#viewTitle"),
  notice: $("#notice"),
  connectionPanel: $("#connectionPanel"),
  connectionTitle: $("#connectionTitle"),
  connectionDetail: $("#connectionDetail"),
  readyCount: $("#readyCount"),
  limitedCount: $("#limitedCount"),
  autoReadyCount: $("#autoReadyCount"),
  nextReset: $("#nextReset"),
  nextResetDetail: $("#nextResetDetail"),
  resetList: $("#resetList"),
  recentEvents: $("#recentEvents"),
  accountsTable: $("#accountsTable"),
  eventsList: $("#eventsList"),
  accountSearch: $("#accountSearch"),
  eventSearch: $("#eventSearch"),
  statusFilter: $("#statusFilter"),
  settingsForm: $("#settingsForm"),
  githubOwner: $("#githubOwner"),
  githubRepo: $("#githubRepo"),
  githubBranch: $("#githubBranch"),
  githubToken: $("#githubToken"),
  rememberToken: $("#rememberToken"),
  accountModal: $("#accountModal"),
  accountForm: $("#accountForm"),
  accountModalTitle: $("#accountModalTitle"),
  accountId: $("#accountId"),
  accountEmail: $("#accountEmail"),
  accountLabel: $("#accountLabel"),
  accountService: $("#accountService"),
  accountPlan: $("#accountPlan"),
  accountNotes: $("#accountNotes"),
  limitModal: $("#limitModal"),
  limitForm: $("#limitForm"),
  limitAccountId: $("#limitAccountId"),
  limitPreview: $("#limitPreview"),
  limitNote: $("#limitNote"),
};

document.addEventListener("DOMContentLoaded", () => {
  hydrateSettingsForm();
  bindEvents();
  render();
  if (isConfigured()) loadFromGitHub();
});

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  $("#refreshButton").addEventListener("click", () => loadFromGitHub());
  $("#openAddAccount").addEventListener("click", () => openAccountModal());
  $("#closeAccountModal").addEventListener("click", () => els.accountModal.close());
  $("#cancelAccount").addEventListener("click", () => els.accountModal.close());
  $("#closeLimitModal").addEventListener("click", () => els.limitModal.close());
  $("#cancelLimit").addEventListener("click", () => els.limitModal.close());
  $("#clearToken").addEventListener("click", clearToken);
  $("#initializeData").addEventListener("click", initializeDataFiles);
  els.settingsForm.addEventListener("submit", handleSettingsSubmit);
  els.accountForm.addEventListener("submit", handleAccountSubmit);
  els.limitForm.addEventListener("submit", handleLimitSubmit);
  els.accountSearch.addEventListener("input", (event) => {
    state.filters.accounts = event.target.value.trim().toLowerCase();
    renderAccounts();
  });
  els.eventSearch.addEventListener("input", (event) => {
    state.filters.events = event.target.value.trim().toLowerCase();
    renderEvents();
  });
  els.statusFilter.addEventListener("change", (event) => {
    state.filters.status = event.target.value;
    renderAccounts();
  });
}

function loadConfig() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

function saveConfig(config) {
  state.config = config;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

function hydrateSettingsForm() {
  els.githubOwner.value = state.config.owner || "shihuiarenjinba-png";
  els.githubRepo.value = state.config.repo || "AI-keeper";
  els.githubBranch.value = state.config.branch || "main";
  els.githubToken.value = state.token ? "saved-token" : "";
  els.rememberToken.checked = Boolean(state.token);
}

function isConfigured() {
  return Boolean(state.config.owner && state.config.repo && state.config.branch && state.token);
}

function githubHeaders() {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${state.token}`,
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

function contentUrl(path) {
  const { owner, repo, branch } = state.config;
  return `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents/${path}?ref=${encodeURIComponent(branch)}`;
}

async function loadFromGitHub() {
  if (!isConfigured()) {
    showNotice("接続設定を入力してください。", "error");
    setView("settings");
    return;
  }
  try {
    showNotice("GitHubから読み込み中です。");
    const accountsFile = await fetchJsonFile(DATA_PATHS.accounts, { accounts: [] });
    const eventsFile = await fetchJsonFile(DATA_PATHS.events, { events: [] });
    const settingsFile = await fetchJsonFile(DATA_PATHS.settings, DEFAULT_SETTINGS);
    state.accounts = Array.isArray(accountsFile.data.accounts) ? accountsFile.data.accounts : [];
    state.events = Array.isArray(eventsFile.data.events) ? eventsFile.data.events : [];
    state.settings = settingsFile.data.services ? settingsFile.data : DEFAULT_SETTINGS;
    state.shas = {
      [DATA_PATHS.accounts]: accountsFile.sha,
      [DATA_PATHS.events]: eventsFile.sha,
      [DATA_PATHS.settings]: settingsFile.sha,
    };
    showNotice("GitHub data repoと同期しました。");
    render();
  } catch (error) {
    showNotice(safeError(error), "error");
  }
}

async function fetchJsonFile(path, fallback) {
  const response = await fetch(contentUrl(path), { headers: githubHeaders() });
  if (response.status === 404) return { data: fallback, sha: null };
  if (!response.ok) throw new Error(`GitHub API error: ${response.status} ${response.statusText}`);
  const payload = await response.json();
  return { data: JSON.parse(decodeBase64(payload.content || "") || "{}"), sha: payload.sha };
}

async function saveJsonFile(path, data, message) {
  const body = {
    message,
    content: encodeBase64(JSON.stringify(data, null, 2) + "\n"),
    branch: state.config.branch,
  };
  if (state.shas[path]) body.sha = state.shas[path];
  const response = await fetch(contentUrl(path).replace(/\?ref=.*/, ""), {
    method: "PUT",
    headers: { ...githubHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`GitHub save failed: ${response.status} ${response.statusText}`);
  const payload = await response.json();
  state.shas[path] = payload.content?.sha || state.shas[path];
}

async function saveAll(message) {
  if (!isConfigured()) {
    showNotice("保存前にGitHub接続設定を完了してください。", "error");
    setView("settings");
    return;
  }
  showNotice("private repoへ保存中です。");
  await saveJsonFile(DATA_PATHS.accounts, { accounts: state.accounts }, message);
  await saveJsonFile(DATA_PATHS.events, { events: state.events }, message);
  showNotice("保存しました。GitHubにcommit履歴も残っています。");
  render();
}

async function initializeDataFiles() {
  if (!isConfigured()) {
    showNotice("初期化前にGitHub接続設定を完了してください。", "error");
    return;
  }
  try {
    await saveJsonFile(DATA_PATHS.accounts, { accounts: state.accounts }, "Initialize accounts data");
    await saveJsonFile(DATA_PATHS.events, { events: state.events }, "Initialize events data");
    await saveJsonFile(DATA_PATHS.settings, state.settings, "Initialize settings data");
    showNotice("dataファイルを初期化しました。");
  } catch (error) {
    showNotice(safeError(error), "error");
  }
}

function handleSettingsSubmit(event) {
  event.preventDefault();
  const tokenValue = els.githubToken.value.trim();
  const nextToken = tokenValue === "saved-token" ? state.token : tokenValue;
  saveConfig({
    owner: els.githubOwner.value.trim(),
    repo: els.githubRepo.value.trim(),
    branch: els.githubBranch.value.trim() || "main",
  });
  state.token = nextToken;
  if (els.rememberToken.checked && nextToken) localStorage.setItem(TOKEN_KEY, nextToken);
  else localStorage.removeItem(TOKEN_KEY);
  hydrateSettingsForm();
  updateConnection();
  loadFromGitHub();
}

function clearToken() {
  state.token = "";
  localStorage.removeItem(TOKEN_KEY);
  els.githubToken.value = "";
  els.rememberToken.checked = false;
  updateConnection();
  showNotice("このブラウザからトークンを削除しました。");
}

function openAccountModal(accountId = "") {
  const account = state.accounts.find((item) => item.id === accountId);
  els.accountModalTitle.textContent = account ? "アカウント編集" : "アカウント追加";
  els.accountId.value = account?.id || "";
  els.accountEmail.value = account?.email || "";
  els.accountLabel.value = account?.label || "";
  els.accountService.value = account?.service || "Codex";
  els.accountPlan.value = account?.plan || "";
  els.accountNotes.value = account?.notes || "";
  els.accountModal.showModal();
}

async function handleAccountSubmit(event) {
  event.preventDefault();
  const id = els.accountId.value || createId("acc");
  const previous = state.accounts.find((item) => item.id === id);
  const account = {
    id,
    email: els.accountEmail.value.trim(),
    label: els.accountLabel.value.trim() || els.accountEmail.value.trim(),
    service: els.accountService.value,
    plan: els.accountPlan.value.trim(),
    status: previous?.status || "ready",
    limitStartedAt: previous?.limitStartedAt || null,
    limitEndsAt: previous?.limitEndsAt || null,
    notes: els.accountNotes.value.trim(),
    updatedAt: new Date().toISOString(),
  };
  state.accounts = previous
    ? state.accounts.map((item) => (item.id === id ? account : item))
    : [account, ...state.accounts];
  addEvent(account, previous ? "account_updated" : "account_created", previous ? "アカウント情報を更新" : "アカウントを追加");
  els.accountModal.close();
  try {
    await saveAll(`${previous ? "Update" : "Add"} ${account.service} account ${account.label}`);
  } catch (error) {
    showNotice(safeError(error), "error");
  }
}

function openLimitModal(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  if (!account) return;
  const start = new Date();
  const end = addDays(start, 7);
  els.limitAccountId.value = accountId;
  els.limitNote.value = "";
  els.limitPreview.textContent = `${account.label || account.email} を ${formatDateTime(start)} から ${formatDateTime(end)} まで制限中として記録します。`;
  els.limitModal.showModal();
}

async function handleLimitSubmit(event) {
  event.preventDefault();
  const account = state.accounts.find((item) => item.id === els.limitAccountId.value);
  if (!account) return;
  const start = new Date();
  const end = addDays(start, 7);
  const updated = { ...account, status: "limited", limitStartedAt: start.toISOString(), limitEndsAt: end.toISOString(), updatedAt: start.toISOString() };
  state.accounts = state.accounts.map((item) => (item.id === account.id ? updated : item));
  addEvent(updated, "limit_started", els.limitNote.value.trim() || "7日制限を開始", {
    limitStartedAt: updated.limitStartedAt,
    limitEndsAt: updated.limitEndsAt,
  });
  els.limitModal.close();
  try {
    await saveAll(`Mark ${updated.service} ${updated.label} limited until ${formatDate(end)}`);
  } catch (error) {
    showNotice(safeError(error), "error");
  }
}

async function markReady(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  if (!account) return;
  const updated = { ...account, status: "ready", limitStartedAt: null, limitEndsAt: null, updatedAt: new Date().toISOString() };
  state.accounts = state.accounts.map((item) => (item.id === accountId ? updated : item));
  addEvent(updated, "limit_cleared", "制限解除として記録");
  try {
    await saveAll(`Mark ${updated.service} ${updated.label} ready`);
  } catch (error) {
    showNotice(safeError(error), "error");
  }
}

async function deleteAccount(accountId) {
  const account = state.accounts.find((item) => item.id === accountId);
  if (!account || !window.confirm(`${account.label || account.email} を削除しますか？履歴ログは残ります。`)) return;
  state.accounts = state.accounts.filter((item) => item.id !== accountId);
  addEvent(account, "account_deleted", "アカウントを削除");
  try {
    await saveAll(`Delete ${account.service} account ${account.label}`);
  } catch (error) {
    showNotice(safeError(error), "error");
  }
}

function addEvent(account, type, note, extra = {}) {
  state.events = [{
    id: createId("evt"),
    accountId: account.id,
    email: account.email,
    label: account.label,
    service: account.service,
    type,
    timestamp: new Date().toISOString(),
    note,
    ...extra,
  }, ...state.events];
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("is-active", button.dataset.view === view));
  document.querySelectorAll(".view").forEach((section) => section.classList.toggle("is-active", section.id === `${view}View`));
  els.viewTitle.textContent = { dashboard: "ダッシュボード", accounts: "アカウント", events: "履歴", settings: "接続設定" }[view];
}

function render() {
  updateConnection();
  renderDashboard();
  renderAccounts();
  renderEvents();
}

function updateConnection() {
  const connected = isConfigured();
  els.connectionPanel.classList.toggle("is-connected", connected);
  els.connectionTitle.textContent = connected ? "接続設定済み" : "未接続";
  els.connectionDetail.textContent = connected ? `${state.config.owner}/${state.config.repo} (${state.config.branch})` : "GitHub data repoを設定してください";
}

function renderDashboard() {
  const readyAccounts = state.accounts.filter((account) => ["ready", "auto_ready"].includes(effectiveStatus(account)));
  const autoReadyAccounts = state.accounts.filter((account) => effectiveStatus(account) === "auto_ready");
  const limitedAccounts = state.accounts
    .filter((account) => effectiveStatus(account) === "limited")
    .sort((a, b) => new Date(a.limitEndsAt) - new Date(b.limitEndsAt));
  els.readyCount.textContent = readyAccounts.length;
  els.limitedCount.textContent = limitedAccounts.length;
  els.autoReadyCount.textContent = autoReadyAccounts.length;
  const next = limitedAccounts[0];
  els.nextReset.textContent = next ? formatDate(next.limitEndsAt) : "-";
  els.nextResetDetail.textContent = next ? `${next.label || next.email} / ${timeLeft(next.limitEndsAt)}` : "予定なし";
  els.resetList.innerHTML = limitedAccounts.length ? limitedAccounts.map(renderResetItem).join("") : `<div class="empty-state">制限中のアカウントはありません。</div>`;
  els.recentEvents.innerHTML = state.events.length ? state.events.slice(0, 8).map(renderEventItem).join("") : `<div class="empty-state">まだ履歴がありません。</div>`;
}

function renderAccounts() {
  const query = state.filters.accounts;
  const status = state.filters.status;
  const accounts = state.accounts.filter((account) => {
    const haystack = `${account.email} ${account.label} ${account.service} ${account.plan}`.toLowerCase();
    const matchesQuery = !query || haystack.includes(query);
    const matchesStatus = status === "all" || effectiveStatus(account) === status;
    return matchesQuery && matchesStatus;
  });
  els.accountsTable.innerHTML = accounts.length ? accounts.map(renderAccountRow).join("") : `<tr><td colspan="6"><div class="empty-state">アカウントがありません。</div></td></tr>`;
  els.accountsTable.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const { action, id } = button.dataset;
      if (action === "limit") openLimitModal(id);
      if (action === "ready") markReady(id);
      if (action === "edit") openAccountModal(id);
      if (action === "delete") deleteAccount(id);
    });
  });
}

function renderEvents() {
  const query = state.filters.events;
  const events = state.events.filter((event) => {
    const haystack = `${event.email} ${event.label} ${event.service} ${event.type} ${event.note}`.toLowerCase();
    return !query || haystack.includes(query);
  });
  els.eventsList.innerHTML = events.length ? events.map(renderEventItem).join("") : `<div class="empty-state">履歴がありません。</div>`;
}

function renderAccountRow(account) {
  const status = effectiveStatus(account);
  const reset = account.limitEndsAt ? formatDateTime(account.limitEndsAt) : "-";
  const remaining = status === "limited" ? timeLeft(account.limitEndsAt) : status === "auto_ready" ? "7日経過" : "-";
  const statusLabel = { ready: "未制限", auto_ready: "自動解除済み", limited: "制限中" }[status];
  const primaryAction = status === "limited" || status === "auto_ready"
    ? `<button class="table-action" data-action="ready" data-id="${account.id}" type="button">解除確定</button>`
    : `<button class="table-action danger" data-action="limit" data-id="${account.id}" type="button">制限開始</button>`;
  return `
    <tr>
      <td><div class="account-cell"><strong>${escapeHtml(account.label || account.email)}</strong><span>${escapeHtml(account.email)}</span></div></td>
      <td><strong>${escapeHtml(account.service)}</strong><div class="muted">${escapeHtml(account.plan || "plan未設定")}</div></td>
      <td><span class="badge ${status}">${statusLabel}</span></td>
      <td>${reset}</td>
      <td>${remaining}</td>
      <td><div class="action-row">${primaryAction}<button class="table-action" data-action="edit" data-id="${account.id}" type="button">編集</button><button class="table-action" data-action="delete" data-id="${account.id}" type="button">削除</button></div></td>
    </tr>
  `;
}

function renderResetItem(account) {
  return `<article class="timeline-item"><header><strong>${escapeHtml(account.label || account.email)}</strong><span class="badge limited">制限中</span></header><p>${escapeHtml(account.service)} / ${formatDateTime(account.limitEndsAt)} 解除予定</p><p>${timeLeft(account.limitEndsAt)}</p></article>`;
}

function renderEventItem(event) {
  return `<article class="event-item"><header><strong>${escapeHtml(eventTypeLabel(event.type))}</strong><span class="badge neutral">${formatDateTime(event.timestamp)}</span></header><p>${escapeHtml(event.label || event.email || "unknown")} / ${escapeHtml(event.service || "-")}</p><p>${escapeHtml(event.note || "")}</p></article>`;
}

function effectiveStatus(account) {
  if (account.status !== "limited") return "ready";
  if (!account.limitEndsAt) return "limited";
  return new Date(account.limitEndsAt).getTime() <= Date.now() ? "auto_ready" : "limited";
}

function eventTypeLabel(type) {
  return {
    account_created: "アカウント追加",
    account_updated: "アカウント更新",
    account_deleted: "アカウント削除",
    limit_started: "制限開始",
    limit_cleared: "制限解除",
  }[type] || type;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ja-JP", { month: "2-digit", day: "2-digit" }).format(new Date(value));
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function timeLeft(value) {
  const diff = Math.max(0, new Date(value).getTime() - Date.now());
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  if (days === 0 && hours === 0) return "まもなく解除";
  if (days === 0) return `残り${hours}時間`;
  return `残り${days}日${hours}時間`;
}

function createId(prefix) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function encodeBase64(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary);
}

function decodeBase64(text) {
  const binary = atob(text.replace(/\n/g, ""));
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeError(error) {
  return String(error?.message || error || "エラーが発生しました").replace(/github_pat_[A-Za-z0-9_]+/g, "github_pat_***");
}

function showNotice(message, type = "info") {
  els.notice.textContent = message;
  els.notice.hidden = false;
  els.notice.classList.toggle("is-error", type === "error");
}
