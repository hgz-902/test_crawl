// 경로 값을 설정한다.
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

// scroll 상태를 저장한다.
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

// 브라우저에서 focus 설정 row 쿼리 동작을 담당한다.
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

// 브라우저에서 restore scroll 상태 동작을 담당한다.
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

// 오케스트레이션 페이지의 탭 전환 UI를 초기화한다.
function initOrchestrationTabs() {
  const tabs = Array.from(document.querySelectorAll("[data-tab-target]"));
  const panels = Array.from(document.querySelectorAll("[data-tab-panel]"));
  if (!tabs.length || !panels.length) return;

  // 브라우저에서 activate 동작을 담당한다.
  function activate(targetId, updateHash = true) {
    const targetPanel = document.getElementById(targetId);
    if (!targetPanel) return;
    tabs.forEach((tab) => {
      const isActive = tab.dataset.tabTarget === targetId;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
      tab.tabIndex = isActive ? 0 : -1;
    });
    panels.forEach((panel) => {
      const isActive = panel.id === targetId;
      panel.hidden = !isActive;
      panel.classList.toggle("is-active", isActive);
    });
    if (updateHash) {
      const url = new URL(window.location.href);
      url.hash = targetId;
      window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    }
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activate(tab.dataset.tabTarget || ""));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const currentIndex = tabs.indexOf(tab);
      let nextIndex = currentIndex;
      if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
      if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      tabs[nextIndex].focus();
      activate(tabs[nextIndex].dataset.tabTarget || "");
    });
  });

  const hashTarget = window.location.hash.replace("#", "");
  if (hashTarget && panels.some((panel) => panel.id === hashTarget)) {
    activate(hashTarget, false);
  } else {
    activate(tabs[0].dataset.tabTarget || "", false);
  }
}

// 등록된 스케줄러 상세 상태를 비동기로 불러와 화면에 반영한다.
function initSchedulerDetailsLazyLoad() {
  const container = document.querySelector("[data-scheduler-status-url]");
  if (!container) return;
  const statusUrl = container.dataset.schedulerStatusUrl;
  if (!statusUrl) return;
  const refreshState = container.querySelector("[data-scheduler-refresh-state]");

  // refresh 상태 값을 설정한다.
  function setRefreshState(state, text) {
    if (!refreshState) return;
    refreshState.textContent = text;
    refreshState.classList.toggle("is-loading", state === "loading");
    refreshState.classList.toggle("is-ready", state === "ready");
    refreshState.classList.toggle("is-error", state === "error");
  }

  setRefreshState("loading", "Windows Scheduler 상태 확인 중");

  fetch(statusUrl, { headers: { Accept: "application/json" } })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      if (!payload || !Array.isArray(payload.scheduler_rows)) return;
      for (const row of payload.scheduler_rows) {
        const taskName = row.task_name || "";
        if (!taskName) continue;
        const tr = document.querySelector(`[data-scheduler-task="${CSS.escape(taskName)}"]`);
        if (!tr) continue;
        for (const field of [
          "scheduler_status",
          "scheduler_last_run_at_display",
          "scheduler_next_run_at_display",
          "scheduler_last_result_display",
          "task_action_path",
        ]) {
          const cell = tr.querySelector(`[data-scheduler-field="${field}"]`);
          if (!cell) continue;
          cell.textContent = row[field] || "-";
          if (field === "scheduler_last_result_display") cell.title = row.scheduler_last_result || "";
        }
      }
      if (payload.scheduler_error) {
        setRefreshState("error", "registry만 표시 중: 실제 Windows 상태 확인 실패");
      } else {
        setRefreshState("ready", "실제 Windows 상태 갱신됨");
      }
    })
    .catch(() => {
      setRefreshState("error", "registry만 표시 중: 실제 Windows 상태 확인 불가");
    });
}

// value를 읽어 반환한다.
function readValue(input) {
  if (input.type === "checkbox") return input.checked;
  if (input.type === "number") return Number(input.value || 0);
  return input.value;
}

// 실행 단계를 정리한다.
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

// 검색 검색어 목록을 읽어 반환한다.
function readSearchTerms(form) {
  const textarea = form.querySelector("[data-search-terms]");
  if (!textarea) return [];
  return textarea.value
    .split(/\r?\n/)
    .map((term) => term.trim())
    .filter(Boolean);
}

// 필터 검색어 목록을 읽어 반환한다.
function readFilterTerms(form) {
  const textarea = form.querySelector("[data-filter-terms]");
  if (!textarea) return [];
  return textarea.value
    .split(/\r?\n/)
    .map((term) => term.trim())
    .filter(Boolean);
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

// 실행 단계 rules를 가져온다.
function getStepRules(action) {
  return STEP_ACTION_RULES[action] || STEP_ACTION_RULES.click;
}

// select options 값을 설정한다.
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

// 실행 단계 row index를 가져온다.
function getStepRowIndex(row) {
  if (!row || !row.parentElement) return 0;
  return Array.from(row.parentElement.querySelectorAll("[data-step-row]")).indexOf(row);
}

// 실행 단계 loop를 현재 설정과 동기화한다.
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
    if (paginationMode.disabled && action !== "click") paginationMode.value = "next_button";
  }
}

// 실행 단계 XPath를 현재 설정과 동기화한다.
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

// 실행 단계 attr를 현재 설정과 동기화한다.
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

// 브라우저에서 renumber 실행 단계 목록 동작을 담당한다.
function renumberSteps() {
  document.querySelectorAll("[data-step-row]").forEach((row, index) => {
    row.querySelector(".step-order").textContent = String(index + 1);
    syncStepXPath(row);
    syncStepLoop(row);
    syncStepAttr(row);
  });
}

// 실행 단계를 읽어 반환한다.
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

// 최초 config JSON을 읽어 UI에 없는 custom 필드도 저장 시 보존한다.
function readInitialConfigPayload(form) {
  const script = form.querySelector("#initial-config-json");
  if (!script || !script.textContent.trim()) return {};
  try {
    const payload = JSON.parse(script.textContent);
    return payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {};
  } catch (_error) {
    return {};
  }
}

// 설정 편집 form 값을 config JSON payload로 조립한다.
function buildPayload(form) {
  const config = readInitialConfigPayload(form);
  form.querySelectorAll("[data-path]").forEach((input) => {
    setPath(config, input.dataset.path, readValue(input));
  });
  config.search_terms = readSearchTerms(form);
  config.filter_terms = readFilterTerms(form);
  config.steps = Array.from(form.querySelectorAll("[data-step-row]")).map(readStep);
  return config;
}

// 실행 단계 row를 생성한다.
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
            <option value="next_button" selected>next_button</option>
            <option value="page_number">page_number</option>
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
  const confirmTarget = (event.submitter && event.submitter.closest("[data-confirm]")) || event.target.closest("[data-confirm]");
  if (confirmTarget && !window.confirm(confirmTarget.dataset.confirm)) {
    event.preventDefault();
    return;
  }

  if (event.target.id === "orchestration-form") {
    guardOrchestrationSchedulerSubmit(event);
    if (event.defaultPrevented) return;
  }

  if (event.target.id === "config-form") {
    const nameInput = event.target.querySelector('[data-path="name"]');
    if (nameInput && nameInput.value) {
      saveScrollState(`/configs/${nameInput.value}`);
    }
    document.getElementById("payload").value = JSON.stringify(buildPayload(event.target));
  }

  showGlobalProgressOverlay(progressMessageForSubmit(event));
});

// 긴 작업 중 화면을 덮는 진행 상태 오버레이를 표시한다.
function showGlobalProgressOverlay(options = {}) {
  const overlay = document.getElementById("global-progress-overlay");
  if (!overlay) return;
  const title = overlay.querySelector("[data-progress-title]");
  const message = overlay.querySelector("[data-progress-message]");
  if (title) title.textContent = options.title || "작업을 처리하는 중입니다";
  if (message) message.textContent = options.message || "요청이 완료될 때까지 잠시 기다려 주세요.";
  overlay.hidden = false;
  document.body.classList.add("is-progress-active");
}

// 제출된 form 종류에 맞는 진행 메시지를 고른다.
function progressMessageForSubmit(event) {
  const form = event.target;
  const submitter = event.submitter;
  const hiddenAction = form.querySelector('input[name="action"]');
  const action = submitter && submitter.name === "action" ? submitter.value : hiddenAction ? hiddenAction.value : "";
  const buttonText = submitter ? submitter.textContent.trim() : "";
  const targetAction = submitter && submitter.formAction ? submitter.formAction : form.action;
  if (form.id === "orchestration-form") {
    const messages = {
      save: ["오케스트레이션 설정 저장 중", "입력한 설정을 JSON 상태 파일에 저장하고 있습니다."],
      run: ["오케스트레이션 수동 실행 중", "선택한 크롤러를 실행하고 결과와 중복 기록을 정리하고 있습니다."],
      sync: ["모니터링 시작 중", "설정을 저장하고 Windows Task Scheduler 작업을 동기화하고 있습니다."],
      stop_monitoring: ["모니터링 종료 중", "이 프로젝트가 관리하는 스케줄러 작업을 종료하고 정리하고 있습니다."],
    };
    if (messages[action]) return { title: messages[action][0], message: messages[action][1] };
  }
  if (form.id === "config-form") {
    if (targetAction && targetAction.includes("/preview")) {
      return { title: "미리보기 실행 중", message: "XPath와 실행 단계 매칭 상태를 확인하고 있습니다." };
    }
    return { title: "크롤러 설정 저장 중", message: "현재 설정 내용을 저장하고 화면을 갱신하고 있습니다." };
  }
  if (targetAction && targetAction.includes("/preview")) {
    return { title: "미리보기 실행 중", message: "XPath와 실행 단계 매칭 상태를 확인하고 있습니다." };
  }
  if (targetAction && targetAction.includes("/run")) {
    return { title: "크롤링 실행 중", message: "외부 사이트 또는 API 응답을 수집하고 결과 파일을 저장하고 있습니다." };
  }
  if (targetAction && targetAction.includes("/delete")) {
    return { title: "삭제 처리 중", message: "선택한 항목을 삭제하고 목록을 갱신하고 있습니다." };
  }
  if (action === "delete_scheduler") {
    return { title: "스케줄러 삭제 중", message: "선택한 Windows Task Scheduler 작업을 삭제하고 상태를 갱신하고 있습니다." };
  }
  return { title: buttonText ? `${buttonText} 처리 중` : "작업을 처리하는 중입니다", message: "요청이 완료될 때까지 잠시 기다려 주세요." };
}

// 모니터링 시작/종료 중복 클릭을 막기 위해 버튼을 잠근다.
function guardOrchestrationSchedulerSubmit(event) {
  const form = event.target;
  const submitter = event.submitter;
  const action = submitter && submitter.name === "action" ? submitter.value : "";
  if (action !== "sync" && action !== "stop_monitoring") return;
  if (form.dataset.schedulerSubmitPending === "true") {
    event.preventDefault();
    return;
  }
  form.dataset.schedulerSubmitPending = "true";
  if (submitter && submitter.name) {
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = submitter.name;
    hidden.value = submitter.value;
    hidden.dataset.schedulerSubmitAction = "true";
    form.appendChild(hidden);
  }
  for (const button of form.querySelectorAll('button[name="action"][value="sync"], button[name="action"][value="stop_monitoring"]')) {
    if (!button.dataset.originalText) button.dataset.originalText = button.textContent.trim();
    if (button === submitter) button.textContent = action === "sync" ? "모니터링 시작 중..." : "모니터링 종료 중...";
    button.disabled = true;
    button.setAttribute("aria-disabled", "true");
    button.classList.add("is-pending");
  }
}

renumberSteps();
initOrchestrationTabs();
initSchedulerDetailsLazyLoad();
if (!focusConfigRowFromQuery()) {
  restoreScrollState();
}
