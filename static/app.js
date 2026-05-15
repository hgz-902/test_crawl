function setPath(target, path, value) {
  const parts = path.split(".");
  let current = target;
  for (let index = 0; index < parts.length - 1; index += 1) {
    const part = parts[index];
    if (!current[part] || typeof current[part] !== "object") current[part] = {};
    current = current[part];
  }
  current[parts[parts.length - 1]] = value;
}

const SCROLL_STATE_KEY = "crawler-manager:scroll-state";

function saveScrollState(targetPath = window.location.pathname) {
  try {
    sessionStorage.setItem(
      SCROLL_STATE_KEY,
      JSON.stringify({
        path: window.location.pathname,
        targetPath,
        scrollX: window.scrollX,
        scrollY: window.scrollY,
      }),
    );
  } catch {
    // Ignore storage failures and let the browser fall back to default behavior.
  }
}

function focusConfigRowFromQuery() {
  try {
    const focus = new URLSearchParams(window.location.search).get("focus");
    if (!focus) return false;

    const link = Array.from(document.querySelectorAll('a[href^="/configs/"]')).find(
      (anchor) => anchor.getAttribute("href") === `/configs/${focus}`,
    );
    if (!link) return false;

    const row = link.closest("tr") || link;
    row.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });

    const url = new URL(window.location.href);
    url.searchParams.delete("focus");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    return true;
  } catch {
    return false;
  }
}

function restoreScrollState() {
  try {
    const raw = sessionStorage.getItem(SCROLL_STATE_KEY);
    if (!raw) return;
    const state = JSON.parse(raw);
    if (!state || typeof state !== "object") return;
    if (state.targetPath !== window.location.pathname && state.path !== window.location.pathname) return;

    window.scrollTo({
      left: Number(state.scrollX || 0),
      top: Number(state.scrollY || 0),
      behavior: "auto",
    });
    sessionStorage.removeItem(SCROLL_STATE_KEY);
  } catch {
    try {
      sessionStorage.removeItem(SCROLL_STATE_KEY);
    } catch {
      // Ignore storage failures.
    }
  }
}

function readValue(input) {
  if (input.type === "checkbox") return input.checked;
  if (input.type === "number") return Number(input.value || 0);
  return input.value;
}

function cleanStep(step) {
  for (const key of Object.keys(step)) {
    if (key === "loop_limit" && step[key] === 0) {
      delete step[key];
      continue;
    }
    if (step[key] === "" || step[key] === null || step[key] === undefined) delete step[key];
  }
  return step;
}

function readSearchTerms(form) {
  const textarea = form.querySelector("[data-search-terms]");
  if (!textarea) return [];
  return textarea.value
    .split(/\r?\n/)
    .map((term) => term.trim())
    .filter(Boolean);
}

function readFilterTerms(form) {
  const textarea = form.querySelector("[data-filter-terms]");
  if (!textarea) return [];
  return textarea.value
    .split(/\r?\n/)
    .map((term) => term.trim())
    .filter(Boolean);
}

function parseNaverStateFromConfig(config) {
  const steps = Array.isArray(config.steps) ? config.steps : [];
  const parserStep = steps.find(
    (step) => step && String(step.action || "").toLowerCase() === "parser" && String(step.attr || "").toLowerCase() === "naver",
  );
  const startUrl = String(config.start_url || "");
  const isNaverUrl = startUrl.includes("openapi.naver.com/v1/search/news");
  const url = isNaverUrl ? new URL(startUrl, window.location.origin) : null;
  const configuredCount = Number(parserStep?.loop_limit || 20);
  return {
    enabled: Boolean(parserStep) || isNaverUrl,
    sort: (url?.searchParams.get("sort") || "date").toLowerCase() === "sim" ? "sim" : "date",
    pageLimit: 1,
    count: Math.min(100, Math.max(1, configuredCount || 20)),
  };
}

function readNaverPanel(form) {
  if (!form.querySelector("[data-naver-enabled]")) return null;
  const count = Math.min(100, Math.max(1, Number(form.querySelector("[data-naver-count]")?.value || 20)));
  return {
    sort: form.querySelector("[data-naver-sort]")?.value === "sim" ? "sim" : "date",
    display: 100,
    pageLimit: 1,
    loopLimit: count,
  };
}

function applyNaverPanelToConfig(config, naver) {
  if (!naver) return config;
  config.start_url = `https://openapi.naver.com/v1/search/news.json?query={search_term}&display=${naver.display}&start=1&sort=${naver.sort}`;
  config.steps = [
    cleanStep({
      name: "naver_news_api",
      action: "parser",
      attr: "naver",
      sort: naver.sort,
      display: naver.display,
      page_limit: naver.pageLimit,
      loop_limit: naver.loopLimit,
    }),
  ];
  return config;
}

function parseDaumStateFromConfig(config) {
  const steps = Array.isArray(config.steps) ? config.steps : [];
  const parserStep = steps.find(
    (step) => step && String(step.action || "").toLowerCase() === "parser" && String(step.attr || "").toLowerCase() === "daum",
  );
  const startUrl = String(config.start_url || "");
  const isDaumUrl = startUrl.includes("dapi.kakao.com/v2/search/web");
  const url = isDaumUrl ? new URL(startUrl, window.location.origin) : null;
  const configuredCount = Number(parserStep?.loop_limit || 20);
  return {
    enabled: Boolean(parserStep) || isDaumUrl,
    sort: (parserStep?.sort || url?.searchParams.get("sort") || "recency").toLowerCase() === "accuracy" ? "accuracy" : "recency",
    pageLimit: 2,
    count: Math.min(100, Math.max(1, configuredCount || 20)),
  };
}

function readDaumPanel(form) {
  if (!form.querySelector("[data-daum-enabled]")) return null;
  const count = Math.min(100, Math.max(1, Number(form.querySelector("[data-daum-count]")?.value || 20)));
  return {
    sort: form.querySelector("[data-daum-sort]")?.value === "accuracy" ? "accuracy" : "recency",
    size: 50,
    pageLimit: 2,
    loopLimit: count,
  };
}

function applyDaumPanelToConfig(config, daum) {
  if (!daum) return config;
  config.start_url = `https://dapi.kakao.com/v2/search/web?query={search_term}+site%3Av.daum.net&sort=${daum.sort}&page=1&size=${daum.size}`;
  config.steps = [
    cleanStep({
      name: "daum_news_api",
      action: "parser",
      attr: "daum",
      sort: daum.sort,
      page_limit: daum.pageLimit,
      loop_limit: daum.loopLimit,
    }),
  ];
  return config;
}

function readInitialConfig() {
  const script = document.getElementById("initial-config-json");
  if (!script) return null;
  try {
    const parsed = JSON.parse(script.textContent || "{}");
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function initNaverPanel() {
  const form = document.getElementById("config-form");
  if (!form) return;
  const config = readInitialConfig() || buildPayload(form);
  const state = parseNaverStateFromConfig(config);
  const enabledInput = form.querySelector("[data-naver-enabled]");
  if (!enabledInput) return;
  enabledInput.checked = state.enabled;
  form.querySelector("[data-naver-sort]").value = state.sort;
  form.querySelector("[data-naver-count]").value = String(state.count || 20);
  form.querySelector("[data-naver-page-limit]").value = String(state.pageLimit || 1);
}

function initDaumPanel() {
  const form = document.getElementById("config-form");
  if (!form) return;
  const config = readInitialConfig() || buildPayload(form);
  const state = parseDaumStateFromConfig(config);
  const enabledInput = form.querySelector("[data-daum-enabled]");
  if (!enabledInput) return;
  enabledInput.checked = state.enabled;
  form.querySelector("[data-daum-sort]").value = state.sort;
  form.querySelector("[data-daum-count]").value = String(state.count || 20);
  form.querySelector("[data-daum-page-limit]").value = String(state.pageLimit || 1);
}

const STEP_ACTION_RULES = {
  click: {
    openMode: [
      { value: "", label: "auto" },
      { value: "same_tab", label: "same_tab" },
      { value: "popup", label: "popup" },
    ],
    attr: [],
    supportsXPath: true,
    supportsLoop: true,
    supportsWait: true,
  },
  goto: {
    openMode: [],
    attr: [
      { value: "href", label: "href" },
      { value: "src", label: "src" },
    ],
    supportsXPath: true,
    supportsLoop: false,
    supportsWait: true,
  },
  download: {
    openMode: [],
    attr: [
      { value: "", label: "auto" },
      { value: "href", label: "href" },
      { value: "src", label: "src" },
    ],
    supportsXPath: true,
    supportsLoop: true,
    supportsWait: true,
  },
  extract: {
    openMode: [],
    attr: [
      { value: "", label: "auto" },
      { value: "href", label: "href" },
      { value: "src", label: "src" },
      { value: "text", label: "text" },
      { value: "html", label: "html" },
    ],
    supportsXPath: true,
    supportsLoop: true,
    supportsWait: true,
  },
  parser: {
    openMode: [],
    attr: [
      { value: "google", label: "google" },
      { value: "naver", label: "naver" },
      { value: "daum", label: "daum" },
    ],
    supportsXPath: false,
    supportsLoop: false,
    supportsLoopLimit: true,
    supportsWait: false,
  },
};

function getStepRules(action) {
  return STEP_ACTION_RULES[action] || STEP_ACTION_RULES.click;
}

function setSelectOptions(select, options, selectedValue) {
  if (!select) return;
  const targetValue = selectedValue ?? "";
  select.replaceChildren();

  for (const optionDef of options) {
    const option = document.createElement("option");
    option.value = optionDef.value;
    option.textContent = optionDef.label;
    select.appendChild(option);
  }

  if (!options.length) {
    select.disabled = true;
    select.value = "";
    return;
  }

  select.disabled = false;
  const hasTarget = options.some((option) => option.value === targetValue);
  select.value = hasTarget ? targetValue : options[0].value;
}

function getStepRowIndex(row) {
  if (!row || !row.parentElement) return 0;
  return Array.from(row.parentElement.querySelectorAll("[data-step-row]")).indexOf(row);
}

function syncStepLoop(row) {
  if (!row) return;
  const action = row.querySelector('[data-step-prop="action"]')?.value || "";
  const rules = getStepRules(action);
  const loopToggle = row.querySelector('[data-step-prop="loop"]');
  const loopMode = row.querySelector('[data-step-prop="loop_mode"]');
  const paginationMode = row.querySelector('[data-step-prop="pagination_mode"]');
  const loopLimit = row.querySelector('[data-step-prop="loop_limit"]');
  const loopToggleLabel = loopToggle?.closest(".step-loop-toggle");
  const loopModeLabel = loopMode?.closest(".step-loop-mode");
  const loopLimitLabel = loopLimit?.closest(".step-loop-limit");
  const enabled = Boolean(loopToggle?.checked) && rules.supportsLoop;
  const cell = row.querySelector("[data-step-xpath-cell]");
  const itemsSection = row.querySelector("[data-step-loop-items]");
  const paginationSection = row.querySelector("[data-step-loop-pagination]");
  const loopConfig = row.querySelector(".step-loop-config");
  const rowIndex = getStepRowIndex(row);
  const allowPagination = rowIndex === 0;
  if (!cell) return;

  cell.classList.toggle("is-loop-enabled", enabled);
  cell.classList.toggle("is-parser-limit-enabled", action === "parser" && Boolean(loopLimit));
  if (loopToggleLabel) loopToggleLabel.hidden = action === "parser";
  if (loopModeLabel) loopModeLabel.hidden = action === "parser";
  if (loopToggle) loopToggle.disabled = !rules.supportsLoop;
  if (loopLimit) loopLimit.disabled = !(rules.supportsLoop || rules.supportsLoopLimit);
  if (loopLimitLabel) loopLimitLabel.hidden = action !== "parser" && !enabled;
  if (!rules.supportsLoop && loopToggle) loopToggle.checked = false;
  if (loopMode) {
    loopMode.disabled = !rules.supportsLoop;
    const loopModeOptions = allowPagination
      ? [
          { value: "items", label: "items" },
          { value: "pagination", label: "pagination" },
        ]
      : [{ value: "items", label: "items" }];
    setSelectOptions(loopMode, loopModeOptions, loopMode.value);
    if (loopMode.disabled || action !== "click") loopMode.value = "items";
  }
  const mode = enabled ? (loopMode?.value || "items") : "";
  if (loopConfig) loopConfig.hidden = action !== "parser" && !enabled;
  if (itemsSection) itemsSection.hidden = !enabled || mode !== "items";
  if (paginationSection) paginationSection.hidden = !enabled || mode !== "pagination";
  if (paginationMode) {
    paginationMode.disabled = !enabled || action !== "click" || mode !== "pagination";
    if (paginationMode.disabled && action !== "click") paginationMode.value = "page_number";
  }
}

function syncStepXPath(row) {
  if (!row) return;
  const action = row.querySelector('[data-step-prop="action"]')?.value || "";
  const rules = getStepRules(action);
  const xpathInputs = [
    row.querySelector('[data-step-prop="xpath"]'),
    row.querySelector('[data-step-prop="xpath_2"]'),
    row.querySelector('[data-step-prop="exclude_xpath"]'),
  ];

  xpathInputs.forEach((input) => {
    if (!input) return;
    input.disabled = !rules.supportsXPath;
  });
}

function syncStepAttr(row) {
  if (!row) return;
  const action = row.querySelector('[data-step-prop="action"]')?.value || "";
  const openModeSelect = row.querySelector('[data-step-prop="open_mode"]');
  const attrSelect = row.querySelector('[data-step-prop="attr"]');
  const waitSelect = row.querySelector('[data-step-prop="wait_state"]');
  const rules = getStepRules(action);

  if (openModeSelect) {
    setSelectOptions(openModeSelect, rules.openMode, openModeSelect.value);
    openModeSelect.disabled = action !== "click" || rules.openMode.length === 0;
    if (openModeSelect.disabled) openModeSelect.value = "";
  }

  if (attrSelect) {
    const selectedValue = action === "goto" && !attrSelect.value ? "href" : attrSelect.value;
    setSelectOptions(attrSelect, rules.attr, selectedValue);
    if (rules.attr.length === 0) {
      attrSelect.value = "";
    }
  }

  if (waitSelect) {
    waitSelect.disabled = !rules.supportsWait;
    if (!rules.supportsWait) {
      waitSelect.value = "";
    }
  }

}

function renumberSteps() {
  document.querySelectorAll("[data-step-row]").forEach((row, index) => {
    row.querySelector(".step-order").textContent = String(index + 1);
    syncStepXPath(row);
    syncStepLoop(row);
    syncStepAttr(row);
  });
}

function readStep(row) {
  const step = {};
  const action = row.querySelector('[data-step-prop="action"]')?.value || "";
  const rules = getStepRules(action);
  const loopModeValue = row.querySelector('[data-step-prop="loop_mode"]')?.value || "items";
  row.querySelectorAll("[data-step-prop]").forEach((input) => {
    if (input.dataset.stepProp === "open_mode" && !rules.openMode.length) return;
    if (input.dataset.stepProp === "attr" && !rules.attr.length) return;
    if ((input.dataset.stepProp === "xpath" || input.dataset.stepProp === "xpath_2" || input.dataset.stepProp === "exclude_xpath") && !rules.supportsXPath) return;
    if (input.dataset.stepProp === "loop" && !rules.supportsLoop) return;
    if (input.dataset.stepProp === "loop_limit" && !(rules.supportsLoop || rules.supportsLoopLimit)) return;
    if (input.dataset.stepProp === "wait_state" && !rules.supportsWait) return;
    if (input.dataset.stepProp === "loop_mode" && !rules.supportsLoop) return;
    if (input.dataset.stepProp === "pagination_mode" && (loopModeValue !== "pagination" || action !== "click")) return;
    const value = readValue(input);
    if (value !== "") step[input.dataset.stepProp] = value;
  });
  if (action !== "click") delete step.open_mode;
  if (action === "click") delete step.attr;
  if (!step.loop) {
    delete step.loop_mode;
    delete step.pagination_mode;
  }
  if (action === "parser") {
    delete step.xpath;
    delete step.xpath_2;
    delete step.exclude_xpath;
    delete step.loop;
    delete step.loop_mode;
    delete step.pagination_mode;
    delete step.open_mode;
    delete step.wait_state;
  }
  if (action === "goto" && !step.attr) step.attr = "href";
  return cleanStep(step);
}

function buildPayload(form) {
  const config = {};
  form.querySelectorAll("[data-path]").forEach((input) => {
    setPath(config, input.dataset.path, readValue(input));
  });
  config.search_terms = readSearchTerms(form);
  config.filter_terms = readFilterTerms(form);
  config.steps = Array.from(form.querySelectorAll("[data-step-row]")).map(readStep);
  applyNaverPanelToConfig(config, readNaverPanel(form));
  applyDaumPanelToConfig(config, readDaumPanel(form));
  return config;
}

function createStepRow() {
  const row = document.createElement("div");
  row.className = "workflow-step";
  row.dataset.stepRow = "";
  row.innerHTML = `
    <span class="step-order"></span>
    <input data-step-prop="name" value="">
    <div class="step-xpath-cell" data-step-xpath-cell>
      <div class="step-xpath-main">
        <input data-step-prop="xpath" value="" placeholder="XPath 1">
      </div>
      <div class="step-xpath-advanced" data-step-loop-items hidden>
        <input data-step-prop="xpath_2" value="" placeholder="XPath 2">
        <div class="step-loop-exclude">
          <div class="step-loop-exclude-field">
            <input data-step-prop="exclude_xpath" value="" placeholder="제외 XPath">
            <span class="step-loop-exclude-icon" title="제외 XPath">ex</span>
          </div>
        </div>
      </div>
      <div class="step-loop-row">
        <label class="step-loop-toggle">
          <input type="checkbox" data-step-prop="loop">
          <span>loop</span>
        </label>
        <div class="step-loop-config" hidden>
          <label class="step-loop-mode">
            <span>mode</span>
            <select data-step-prop="loop_mode">
              <option value="items" selected>items</option>
              <option value="pagination">pagination</option>
            </select>
          </label>
          <label class="step-loop-limit">
            <span>limit</span>
            <input type="number" min="0" data-step-prop="loop_limit" value="" placeholder="max">
          </label>
        </div>
      </div>
      <div class="step-pagination-advanced" data-step-loop-pagination hidden>
        <label class="step-pagination-mode">
          <span>page</span>
          <select data-step-prop="pagination_mode">
            <option value="page_number" selected>page_number</option>
            <option value="next_button">next_button</option>
          </select>
          <button
            type="button"
            class="help-tip"
            title="page pagination은 첫 페이지를 건너뛰고 2페이지부터 이동합니다.&#10;next_button은 다음 버튼을 반복 클릭하고, page_number는 XPath에 {page_number}를 넣어 페이지 번호로 바꿉니다.&#10;예: 1페이지는 현재 상태 유지, 2페이지부터 클릭합니다."
            aria-label="page pagination 설명"
          >?</button>
        </label>
      </div>
    </div>
    <select data-step-prop="action">
      <option value="click">click</option>
      <option value="goto">goto</option>
      <option value="download">download</option>
      <option value="extract">extract</option>
      <option value="parser">parser</option>
    </select>
    <select data-step-prop="open_mode" disabled>
      <option value="">auto</option>
      <option value="same_tab">same_tab</option>
      <option value="popup">popup</option>
    </select>
    <select data-step-prop="attr">
      <option value="">auto</option>
    </select>
    <select data-step-prop="wait_state" class="step-wait-select">
      <option value="">auto</option>
      <option value="attached">attached</option>
      <option value="visible">visible</option>
      <option value="hidden">hidden</option>
      <option value="detached">detached</option>
    </select>
    <div class="step-actions">
      <button type="button" data-step-up>위</button>
      <button type="button" data-step-down>아래</button>
      <button class="danger" type="button" data-remove-step>삭제</button>
    </div>
  `;
  return row;
}

document.addEventListener("click", (event) => {
  const stepList = document.getElementById("workflow-steps");
  if (event.target.closest("[data-add-step]")) {
    stepList.appendChild(createStepRow());
    renumberSteps();
    return;
  }

  const row = event.target.closest("[data-step-row]");
  if (!row) return;

  if (event.target.closest("[data-remove-step]")) {
    row.remove();
    renumberSteps();
  } else if (event.target.closest("[data-step-up]") && row.previousElementSibling) {
    stepList.insertBefore(row, row.previousElementSibling);
    renumberSteps();
  } else if (event.target.closest("[data-step-down]") && row.nextElementSibling) {
    stepList.insertBefore(row.nextElementSibling, row);
    renumberSteps();
  }
});

document.addEventListener("change", (event) => {
  if (event.target.matches('[data-step-prop="loop"]')) {
    const row = event.target.closest("[data-step-row]");
    syncStepLoop(row);
    syncStepXPath(row);
    syncStepAttr(row);
  }
  if (event.target.matches('[data-step-prop="loop_mode"]')) {
    const row = event.target.closest("[data-step-row]");
    syncStepLoop(row);
  }
  if (event.target.matches('[data-step-prop="action"]')) {
    const row = event.target.closest("[data-step-row]");
    syncStepXPath(row);
    syncStepAttr(row);
    syncStepLoop(row);
  }
  if (event.target.matches('[data-step-prop="open_mode"]')) {
    const row = event.target.closest("[data-step-row]");
    syncStepAttr(row);
  }
});

document.addEventListener("submit", (event) => {
  const confirmForm = event.submitter?.closest("[data-confirm]") || event.target.closest("[data-confirm]");
  if (confirmForm && !window.confirm(confirmForm.dataset.confirm)) {
    event.preventDefault();
    return;
  }

  if (event.target.id === "config-form") {
    const nameInput = event.target.querySelector('[data-path="name"]');
    if (nameInput && nameInput.value) {
      saveScrollState(`/configs/${nameInput.value}`);
    }
    document.getElementById("payload").value = JSON.stringify(buildPayload(event.target));
  }
});

renumberSteps();
initNaverPanel();
initDaumPanel();
if (!focusConfigRowFromQuery()) {
  restoreScrollState();
}
