const USER_ID = "unknown";
const PAGE_SIZE = 20;
const AUTO_REFRESH_MS = 60000;

const CATEGORY_ITEMS = [
  { code: "all", label: "전체" },
  { code: "favorite", label: "즐겨찾기" },
  { code: "SK", label: "SK" },
  { code: "SKI", label: "SKI" },
  { code: "SKE", label: "SKE" },
  { code: "SKGC", label: "SKGC" },
  { code: "SKEN", label: "SKEN" },
  { code: "SKEO", label: "SKEO" },
  { code: "SKO", label: "SKO" },
  { code: "SKIET", label: "SKIET" },
  { code: "E&S", label: "E&S" },
];

const state = {
  category: "all",
  page: 1,
  pageSize: PAGE_SIZE,
  grouped: true,
  autoRefresh: false,
  fromDate: "",
  toDate: "",
  source: "",
  filterTerm: "",
  title: "",
  options: { sources: [], filter_terms: [] },
  picker: { type: "", pendingValue: "" },
  admin: { category: "SK", detail: null },
  autoTimer: null,
  lastItems: [],
};

const els = {};

document.addEventListener("DOMContentLoaded", () => {
  bindElements();
  setDefaultDates();
  renderCategories();
  bindEvents();
  boot();
});

function bindElements() {
  [
    "categoryList",
    "statTotal",
    "statDirect",
    "statNegative",
    "fromDate",
    "toDate",
    "sourcePickerBtn",
    "termPickerBtn",
    "titleSearch",
    "searchBtn",
    "selectedCompany",
    "selectedSource",
    "groupToggle",
    "autoRefreshToggle",
    "refreshBtn",
    "resultSummary",
    "statusText",
    "newsBody",
    "topPager",
    "bottomPager",
    "pickerModal",
    "pickerTitle",
    "pickerCloseBtn",
    "pickerResetBtn",
    "pickerApplyBtn",
    "pickerGrid",
    "analysisModal",
    "analysisTitle",
    "analysisCloseBtn",
    "analysisContent",
    "adminModal",
    "adminTitle",
    "adminCloseBtn",
    "adminCategoryList",
    "adminKeywordTitle",
    "adminReloadBtn",
    "adminKeywordInput",
    "adminSaveBtn",
    "adminAppendBtn",
    "adminDeleteAllBtn",
    "adminKeywordList",
    "settingsBtn",
    "adminBtn",
    "toast",
  ].forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function setDefaultDates() {
  const today = new Date();
  const weekAgo = new Date(today);
  weekAgo.setDate(today.getDate() - 7);
  els.fromDate.value = formatDateInput(weekAgo);
  els.toDate.value = formatDateInput(today);
  state.fromDate = els.fromDate.value;
  state.toDate = els.toDate.value;
}

function bindEvents() {
  els.searchBtn.addEventListener("click", () => {
    readFilters();
    state.page = 1;
    loadAll();
  });
  els.refreshBtn.addEventListener("click", () => loadAll());
  els.sourcePickerBtn.addEventListener("click", () => openPicker("source"));
  els.termPickerBtn.addEventListener("click", () => openPicker("filterTerm"));
  els.pickerCloseBtn.addEventListener("click", closePicker);
  els.pickerResetBtn.addEventListener("click", resetPickerSelection);
  els.pickerApplyBtn.addEventListener("click", applyPickerSelection);
  els.groupToggle.addEventListener("change", () => {
    state.grouped = els.groupToggle.checked;
    state.page = 1;
    loadNews();
  });
  els.autoRefreshToggle.addEventListener("change", () => {
    state.autoRefresh = els.autoRefreshToggle.checked;
    configureAutoRefresh();
  });
  els.analysisCloseBtn.addEventListener("click", closeAnalysis);
  els.settingsBtn.addEventListener("click", () => showToast("카테고리 키워드 설정 API는 준비되어 있지만, 이 프로토타입에서는 별도 설정 화면을 열지 않습니다."));
  els.adminBtn.addEventListener("click", openAdmin);
  els.adminCloseBtn.addEventListener("click", closeAdmin);
  els.adminReloadBtn.addEventListener("click", () => loadAdminCategory(state.admin.category));
  els.adminSaveBtn.addEventListener("click", saveAdminKeywords);
  els.adminAppendBtn.addEventListener("click", appendAdminKeywords);
  els.adminDeleteAllBtn.addEventListener("click", deleteAdminCategoryKeywords);
}

async function boot() {
  await loadOptions();
  await loadCategoryKeywords();
  await loadAll();
}

function renderCategories() {
  els.categoryList.innerHTML = "";
  CATEGORY_ITEMS.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "category-btn";
    button.dataset.category = item.code;
    button.textContent = item.label;
    button.addEventListener("click", () => {
      state.category = item.code;
      state.page = 1;
      renderCategories();
      updateSelectionLabels();
      loadAll();
    });
    if (state.category === item.code) {
      button.classList.add("active");
    }
    els.categoryList.appendChild(button);
  });
}

async function loadOptions() {
  try {
    const data = await apiGet("/api/filter-options");
    state.options.sources = data.sources || [];
    state.options.filter_terms = data.filter_terms || data.search_terms || [];
  } catch (error) {
    showToast(`필터 옵션 조회 실패: ${error.message}`);
  }
}

async function loadCategoryKeywords() {
  try {
    await apiGet("/api/category-keywords");
  } catch (error) {
    // 카테고리 키워드는 없을 수 있다. 목록 조회 실패가 전체 UI를 막지는 않는다.
  }
}

function openAdmin() {
  renderAdminCategories();
  els.adminModal.hidden = false;
  loadAdminCategory(state.admin.category);
}

function closeAdmin() {
  els.adminModal.hidden = true;
}

function renderAdminCategories() {
  const categories = CATEGORY_ITEMS.filter((item) => !["all", "favorite"].includes(item.code));
  els.adminCategoryList.innerHTML = categories.map((item) => `
    <button type="button" class="admin-category-btn ${state.admin.category === item.code ? "active" : ""}" data-admin-category="${escapeAttribute(item.code)}">${escapeHtml(item.label)}</button>
  `).join("");
  els.adminCategoryList.querySelectorAll("[data-admin-category]").forEach((button) => {
    button.addEventListener("click", () => {
      state.admin.category = button.dataset.adminCategory || "SK";
      renderAdminCategories();
      loadAdminCategory(state.admin.category);
    });
  });
}

async function loadAdminCategory(categoryCode) {
  els.adminKeywordTitle.textContent = `${categoryCode} 단어 목록`;
  els.adminKeywordList.innerHTML = `<div class="analysis-block">저장된 단어를 불러오는 중입니다.</div>`;
  try {
    const detail = await apiGet(`/api/category-keywords/${encodeURIComponent(categoryCode)}`);
    state.admin.detail = detail;
    const keywords = (detail.keywords || []).map((item) => item.keyword).filter(Boolean);
    els.adminKeywordInput.value = keywords.join("\n");
    renderAdminKeywordList(detail.keywords || []);
  } catch (error) {
    state.admin.detail = null;
    els.adminKeywordInput.value = "";
    els.adminKeywordList.innerHTML = `<div class="analysis-block">단어 목록 조회 실패: ${escapeHtml(error.message)}</div>`;
  }
}

function renderAdminKeywordList(keywordItems) {
  if (!keywordItems.length) {
    els.adminKeywordList.innerHTML = `<div class="analysis-block">아직 저장된 단어가 없습니다.</div>`;
    return;
  }
  els.adminKeywordList.innerHTML = keywordItems.map((item) => `
    <div class="keyword-item">
      <span title="${escapeAttribute(item.keyword)}">${escapeHtml(item.keyword)}</span>
      <button type="button" class="keyword-delete-btn" data-keyword-id="${escapeAttribute(item.keyword_id)}" aria-label="단어 삭제">X</button>
    </div>
  `).join("");
  els.adminKeywordList.querySelectorAll("[data-keyword-id]").forEach((button) => {
    button.addEventListener("click", () => deleteAdminKeyword(button.dataset.keywordId || ""));
  });
}

async function saveAdminKeywords() {
  const category = state.admin.category;
  const keywords = parseKeywordInput();
  try {
    await apiJson(`/api/category-keywords/${encodeURIComponent(category)}`, {
      method: "PUT",
      body: { keywords },
    });
    showToast(`${category} 단어 목록을 저장했습니다.`);
    await loadAdminCategory(category);
    await loadCategoryKeywords();
    if (state.category === category) await loadAll();
  } catch (error) {
    showToast(`단어 저장 실패: ${error.message}`);
  }
}

async function appendAdminKeywords() {
  const category = state.admin.category;
  const keywords = parseKeywordInput();
  if (!keywords.length) {
    showToast("추가할 단어를 입력하세요.");
    return;
  }
  try {
    await apiJson(`/api/category-keywords/${encodeURIComponent(category)}/keywords`, {
      method: "POST",
      body: { keywords },
    });
    showToast(`${category} 단어를 추가했습니다.`);
    await loadAdminCategory(category);
    await loadCategoryKeywords();
    if (state.category === category) await loadAll();
  } catch (error) {
    showToast(`단어 추가 실패: ${error.message}`);
  }
}

async function deleteAdminKeyword(keywordId) {
  if (!keywordId) return;
  try {
    await apiJson(`/api/category-keywords/keywords/${encodeURIComponent(keywordId)}`, {
      method: "DELETE",
    });
    showToast("단어를 삭제했습니다.");
    await loadAdminCategory(state.admin.category);
    await loadCategoryKeywords();
    if (state.category === state.admin.category) await loadAll();
  } catch (error) {
    showToast(`단어 삭제 실패: ${error.message}`);
  }
}

async function deleteAdminCategoryKeywords() {
  const category = state.admin.category;
  try {
    await apiJson(`/api/category-keywords/${encodeURIComponent(category)}`, {
      method: "DELETE",
    });
    showToast(`${category} 단어 목록을 모두 삭제했습니다.`);
    await loadAdminCategory(category);
    await loadCategoryKeywords();
    if (state.category === category) await loadAll();
  } catch (error) {
    showToast(`단어 전체 삭제 실패: ${error.message}`);
  }
}

function parseKeywordInput() {
  const seen = new Set();
  const keywords = [];
  els.adminKeywordInput.value
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean)
    .forEach((value) => {
      const key = value.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        keywords.push(value);
      }
    });
  return keywords;
}

async function loadAll() {
  await Promise.all([loadStats(), loadNews()]);
}

async function loadStats() {
  const params = buildBaseParams();
  try {
    const data = await apiGet(`/api/stats?${params.toString()}`);
    els.statTotal.textContent = formatNumber(data.total || 0);
  } catch (error) {
    els.statTotal.textContent = "0";
  }
}

async function loadNews() {
  setStatus("조회 중...");
  const endpoint = state.grouped ? "/api/news/grouped" : "/api/news";
  const params = buildBaseParams();
  params.set("page", String(state.page));
  params.set("page_size", String(state.pageSize));
  params.set("sort_by", "published_at");
  params.set("sort_order", "desc");

  try {
    const data = await apiGet(`${endpoint}?${params.toString()}`);
    state.lastItems = data.items || [];
    renderTable(data);
    renderPager(data);
    renderClientStats(data.items || []);
    updateSelectionLabels();
    setStatus("");
  } catch (error) {
    els.newsBody.innerHTML = `<tr><td colspan="11" class="empty-cell">기사 목록 조회 실패: ${escapeHtml(error.message)}</td></tr>`;
    els.resultSummary.textContent = "조회 실패";
    els.topPager.innerHTML = "";
    els.bottomPager.innerHTML = "";
    setStatus("오류");
  }
}

function buildBaseParams() {
  readFilters();
  const params = new URLSearchParams({ user_id: USER_ID });
  if (state.fromDate) params.set("from_date", state.fromDate);
  if (state.toDate) params.set("to_date", state.toDate);
  if (state.title) params.set("title", state.title);
  if (state.source) params.set("source", state.source);
  if (state.filterTerm) params.set("filter_term", state.filterTerm);
  if (state.category === "favorite") {
    params.set("favorite_status", "favorite");
  } else if (state.category !== "all") {
    params.set("category_code", state.category);
  }
  return params;
}

function readFilters() {
  state.fromDate = els.fromDate.value || "";
  state.toDate = els.toDate.value || "";
  state.title = els.titleSearch.value.trim();
}

function renderTable(data) {
  const items = data.items || [];
  const total = data.totalCount || 0;
  els.resultSummary.textContent = `총 ${formatNumber(total)}건, ${data.page || state.page}페이지`;
  if (!items.length) {
    els.newsBody.innerHTML = `<tr><td colspan="11" class="empty-cell">검색 결과가 없습니다.</td></tr>`;
    return;
  }
  const rows = [];
  items.forEach((item, idx) => {
    const number = ((data.page || 1) - 1) * (data.pageSize || PAGE_SIZE) + idx + 1;
    rows.push(renderArticleRow(item, number, false));
    if (state.grouped && Array.isArray(item.similar_articles) && item.similar_articles.length) {
      item.similar_articles.forEach((similar) => rows.push(renderArticleRow(similar, "", true)));
    }
  });
  els.newsBody.innerHTML = rows.join("");
  bindRowActions();
}

function renderArticleRow(item, number, isSimilar) {
  const category = inferCategory(item);
  const sentiment = normalizeSentiment(item.sentiment);
  const importance = inferImportance(item);
  const published = formatPublishedAt(item.published_at);
  const related = item.filter_term || "-";
  const url = item.url || "#";
  const similarClass = isSimilar ? " class=\"similar-row\"" : "";
  const titleClass = isSimilar ? "similar-title" : "";
  return `
    <tr${similarClass}>
      <td>${escapeHtml(String(number))}</td>
      <td><span class="pill">${escapeHtml(category)}</span></td>
      <td class="${titleClass}">
        <a class="title-link" href="${escapeAttribute(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title || "(제목 없음)")}</a>
        ${isSimilar ? `<div class="subtext">유사 기사</div>` : similarCountText(item)}
      </td>
      <td><div class="stack-cell"><strong class="${sentiment.className}">${sentiment.label}</strong><span class="subtext">AI</span></div></td>
      <td><div class="stack-cell"><strong>${escapeHtml(importance)}</strong><span class="subtext">AI</span></div></td>
      <td>${escapeHtml(item.source_name || "-")}</td>
      <td>${escapeHtml(related)}</td>
      <td>${escapeHtml(published)}</td>
      <td><button type="button" class="action-btn ${item.is_read ? "active" : ""}" data-action="read" data-id="${escapeAttribute(item.article_id)}">${item.is_read ? "확인" : "-"}</button></td>
      <td><button type="button" class="action-btn ai" data-action="analysis" data-id="${escapeAttribute(item.article_id)}">AI</button></td>
      <td><button type="button" class="action-btn ${item.is_favorite ? "active" : ""}" data-action="favorite" data-id="${escapeAttribute(item.article_id)}">${item.is_favorite ? "★" : "☆"}</button></td>
    </tr>
  `;
}

function similarCountText(item) {
  const count = Number(item.similar_count || 0);
  return count > 0 ? `<div class="subtext">유사 기사 ${count}건</div>` : "";
}

function bindRowActions() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.id;
      const action = button.dataset.action;
      if (!id) return;
      if (action === "analysis") {
        openAnalysis(id);
        return;
      }
      const current = button.classList.contains("active");
      await toggleArticleState(id, action, !current);
    });
  });
}

async function toggleArticleState(articleId, action, value) {
  try {
    await apiJson(`/api/news/${encodeURIComponent(articleId)}/${action}`, {
      method: "PATCH",
      body: { user_id: USER_ID, value },
    });
    await loadAll();
  } catch (error) {
    showToast(`상태 변경 실패: ${error.message}`);
  }
}

async function openAnalysis(articleId) {
  els.analysisContent.innerHTML = `<div class="analysis-block">분석 내용을 불러오는 중입니다.</div>`;
  els.analysisModal.hidden = false;
  try {
    const data = await apiGet(`/api/news/${encodeURIComponent(articleId)}/analysis?user_id=${encodeURIComponent(USER_ID)}`);
    if (!data) {
      els.analysisContent.innerHTML = `<div class="analysis-block">저장된 분석 결과가 없습니다. AI 분석 실행 API는 현재 이 프로토타입 범위에서 제외되어 있습니다.</div>`;
      return;
    }
    els.analysisContent.innerHTML = `
      <div class="analysis-block"><h3>감성</h3><div>${escapeHtml(data.sentiment_label || "-")}</div></div>
      <div class="analysis-block"><h3>대응 방안</h3><div>${escapeHtml(data.action_plan || "-").replaceAll("\n", "<br>")}</div></div>
      <div class="analysis-block"><h3>파급 효과</h3><div>${escapeHtml(data.impact || "-").replaceAll("\n", "<br>")}</div></div>
    `;
  } catch (error) {
    els.analysisContent.innerHTML = `<div class="analysis-block">분석 조회 실패: ${escapeHtml(error.message)}</div>`;
  }
}

function closeAnalysis() {
  els.analysisModal.hidden = true;
}

function renderPager(data) {
  const page = Number(data.page || state.page || 1);
  const pageSize = Number(data.pageSize || state.pageSize || PAGE_SIZE);
  const total = Number(data.totalCount || 0);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const html = pagerHtml(page, totalPages);
  els.topPager.innerHTML = html;
  els.bottomPager.innerHTML = html;
  document.querySelectorAll(".page-btn[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextPage = Number(button.dataset.page);
      if (nextPage && nextPage !== state.page) {
        state.page = nextPage;
        loadNews();
      }
    });
  });
}

function pagerHtml(page, totalPages) {
  const pages = [];
  const start = Math.max(1, page - 4);
  const end = Math.min(totalPages, start + 8);
  pages.push(`<button type="button" class="page-btn" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>이전</button>`);
  for (let p = start; p <= end; p += 1) {
    pages.push(`<button type="button" class="page-btn ${p === page ? "active" : ""}" data-page="${p}">${p}</button>`);
  }
  pages.push(`<button type="button" class="page-btn" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""}>다음</button>`);
  return pages.join("");
}

function renderClientStats(items) {
  const direct = items.filter((item) => String(item.filter_term || "").trim()).length;
  const negative = items.filter((item) => normalizeSentiment(item.sentiment).label === "부정").length;
  els.statDirect.textContent = formatNumber(direct);
  els.statNegative.textContent = formatNumber(negative);
}

function openPicker(type) {
  state.picker.type = type;
  state.picker.pendingValue = type === "source" ? state.source : state.filterTerm;
  const isSource = type === "source";
  els.pickerTitle.textContent = isSource ? "출처 선택" : "검색어 선택";
  const values = isSource ? state.options.sources : state.options.filter_terms;
  if (!values.length) {
    els.pickerGrid.innerHTML = `<div class="analysis-block">선택 가능한 항목이 없습니다.</div>`;
  } else {
    els.pickerGrid.innerHTML = values.map((value) => `
      <button type="button" class="picker-option ${value === state.picker.pendingValue ? "active" : ""}" data-value="${escapeAttribute(value)}">${escapeHtml(value)}</button>
    `).join("");
    els.pickerGrid.querySelectorAll(".picker-option").forEach((button) => {
      button.addEventListener("click", () => {
        state.picker.pendingValue = button.dataset.value || "";
        els.pickerGrid.querySelectorAll(".picker-option").forEach((node) => node.classList.remove("active"));
        button.classList.add("active");
      });
    });
  }
  els.pickerModal.hidden = false;
}

function closePicker() {
  els.pickerModal.hidden = true;
}

function resetPickerSelection() {
  state.picker.pendingValue = "";
  els.pickerGrid.querySelectorAll(".picker-option").forEach((node) => node.classList.remove("active"));
}

function applyPickerSelection() {
  if (state.picker.type === "source") {
    state.source = state.picker.pendingValue;
  } else if (state.picker.type === "filterTerm") {
    state.filterTerm = state.picker.pendingValue;
  }
  state.page = 1;
  closePicker();
  updateSelectionLabels();
  loadAll();
}

function updateSelectionLabels() {
  const category = CATEGORY_ITEMS.find((item) => item.code === state.category);
  els.selectedCompany.textContent = `선택 회사: ${category ? category.label : "전체"}`;
  els.selectedSource.textContent = `선택 출처: ${state.source || "전체"}`;
  els.sourcePickerBtn.textContent = state.source || "출처를 선택...";
  els.termPickerBtn.textContent = state.filterTerm || "검색어를 선택...";
}

function configureAutoRefresh() {
  if (state.autoTimer) {
    window.clearInterval(state.autoTimer);
    state.autoTimer = null;
  }
  if (state.autoRefresh) {
    state.autoTimer = window.setInterval(() => loadAll(), AUTO_REFRESH_MS);
    showToast("자동 새로고침이 켜졌습니다.");
  }
}

function inferCategory(item) {
  const selectedCategory = categoryLabelForCode(state.category);
  if (selectedCategory) return selectedCategory;

  const apiCategory = categoryLabelForCode(item.category_code);
  if (apiCategory) return apiCategory;

  const filterTokens = String(item.filter_term || "")
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);
  const candidates = CATEGORY_ITEMS
    .filter((candidate) => !["all", "favorite"].includes(candidate.code))
    .sort((a, b) => b.code.length - a.code.length);
  return candidates.find((candidate) => filterTokens.includes(candidate.code.toUpperCase()))?.label || "SK";
}

function categoryLabelForCode(code) {
  const normalized = String(code || "").trim().toUpperCase();
  if (!normalized || normalized === "ALL" || normalized === "FAVORITE") return "";
  return CATEGORY_ITEMS.find((item) => item.code.toUpperCase() === normalized)?.label || "";
}

function normalizeSentiment(value) {
  const raw = String(value || "neutral").toLowerCase();
  if (raw === "positive") return { label: "긍정", className: "sentiment-positive" };
  if (raw === "negative") return { label: "부정", className: "sentiment-negative" };
  return { label: "중립", className: "sentiment-neutral" };
}

function inferImportance(item) {
  const title = String(item.title || "");
  const related = String(item.filter_term || "");
  const negative = normalizeSentiment(item.sentiment).label === "부정";
  const hits = related.split(",").map((value) => value.trim()).filter(Boolean).length;
  if (negative || hits >= 4 || /사고|수사|소송|화재|구속|급락|적자|파업/.test(title)) return "Level 1";
  if (hits >= 2 || /투자|합병|인수|정책|규제|배터리|반도체/.test(title)) return "Level 2";
  return "Level 3";
}

function formatPublishedAt(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 16);
}

function formatDateInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("ko-KR");
}

function setStatus(message) {
  els.statusText.textContent = message;
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 3200);
}

async function apiGet(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function apiJson(url, options) {
  const response = await fetch(url, {
    method: options.method || "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(options.body || {}),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}
