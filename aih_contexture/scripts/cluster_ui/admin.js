"use strict";

const $ = (id) => document.getElementById(id);
const states = {
  queued: ["排队中", "queued"],
  running: ["处理中", "running"],
  done: ["已完成", "done"],
  failed: ["失败", "failed"],
  cancelled: ["已取消", "cancelled"],
  retry: ["重新派发", "queued"],
};
const nodeNames = {
  amd66: ["AMD", "192.168.31.66"],
  intel88: ["Intel", "192.168.31.88"],
  mac100: ["Mac", "192.168.31.100"],
};
const titles = {
  overview: "处理总览",
  tasks: "任务管理",
  nodes: "工作节点",
  settings: "运行配置",
};
const kinds = {
  book: "整书任务",
  group: "多文件任务组",
  prepare: "读取与分批",
  extract: "版面与文字识别",
  merge: "整书合并",
  legacy: "直接处理",
};
let authenticated = false;
let csrf = "";
let overview = null;
let currentPage = "overview";
let offset = 0;
let selectedTask = null;
let detailGeneration = 0;
let refreshController = null;
let toastTimer = null;
let pendingConfirmation = null;
let files = [];
let uploading = false;
let uploadSettings = null;

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );
}
function badge(state) {
  const [label, className] = states[state] || ["未知", "cancelled"];
  return /* HTML */ `<span class="badge ${className}">${label}</span>`;
}
function nameOf(job) {
  if (job.kind === "group") return `任务组 · ${job.children.length} 份文献`;
  return job.details.filename || `历史任务 · ${job.id.slice(0, 8)}`;
}
function date(value) {
  return value
    ? new Date(value * 1000).toLocaleString("zh-CN", { hour12: false })
    : "—";
}
function duration(seconds) {
  if (seconds < 60) return `${Math.max(0, Math.floor(seconds))}秒`;
  if (seconds < 3600)
    return `${Math.floor(seconds / 60)}分${Math.floor(seconds % 60)}秒`;
  return `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分`;
}
function bytes(value) {
  return value >= 1048576
    ? `${(value / 1048576).toFixed(1)} MiB`
    : `${Math.ceil(value / 1024)} KiB`;
}
function nodeLabel(id) {
  return nodeNames[id]?.[0] || id || "—";
}
function toast(message) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 5500);
}
function showLogin(message = "") {
  authenticated = false;
  csrf = "";
  overview = null;
  selectedTask = null;
  refreshController?.abort();
  document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
  $("boot").hidden = true;
  $("app").hidden = true;
  $("login").hidden = false;
  $("login-error").textContent = message;
  [
    "metrics",
    "overview-nodes",
    "recent-tasks",
    "task-table",
    "node-list",
    "detail-body",
  ].forEach((id) => {
    $(id).replaceChildren();
  });
}
async function api(url, options = {}) {
  const { authRedirect = true, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});
  if (fetchOptions.method && fetchOptions.method !== "GET")
    headers.set("X-CSRF-Token", csrf);
  if (
    fetchOptions.body &&
    typeof fetchOptions.body === "object" &&
    !(fetchOptions.body instanceof File)
  ) {
    headers.set("Content-Type", "application/json");
    fetchOptions.body = JSON.stringify(fetchOptions.body);
  }
  const response = await fetch(url, {
    ...fetchOptions,
    headers,
    credentials: "same-origin",
  });
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && authRedirect)
      showLogin("登录已过期，请重新登录");
    const error = new Error(result.error || "请求失败");
    error.status = response.status;
    throw error;
  }
  return result;
}
function stage(job) {
  if (job.status !== "running") return states[job.status]?.[0] || "等待处理";
  const active = job.children.find((child) => child.status === "running");
  return active ? kinds[active.kind] || "处理中" : kinds[job.kind] || "处理中";
}
function progress(job) {
  const { completed_pages: done, total_pages: total } = job.progress;
  if (!total)
    return /* HTML */ `<span class="muted">${escapeHtml(stage(job))}</span>`;
  const percentage = Math.round((done / total) * 100);
  return /* HTML */ `<div class="progress-cell">
    <progress value="${done}" max="${total}" aria-label="已处理页面"></progress>
    <div class="progress-copy">
      <span>${done} / ${total} 页</span><span>${percentage}%</span>
    </div>
  </div>`;
}
function taskTable(items) {
  if (!items.length) return '<div class="empty">暂无符合条件的任务</div>';
  return /* HTML */ `<table>
    <thead>
      <tr>
        <th>文献 / 任务组</th>
        <th>状态</th>
        <th>页面进度</th>
        <th>登记时间</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      ${items
        .map(
          (job) =>
            `<tr data-job="${escapeHtml(job.id)}" tabindex="0" aria-label="查看 ${escapeHtml(nameOf(job))}"><td><div class="file-cell"><span class="file-icon">${job.kind === "group" ? "ZIP" : "PDF"}</span><div><div class="file-name" title="${escapeHtml(nameOf(job))}">${escapeHtml(nameOf(job))}</div><div class="file-meta">${escapeHtml(job.id.slice(0, 12))} · ${escapeHtml(kinds[job.kind] || "任务")}</div></div></div></td><td>${badge(job.status)}</td><td>${progress(job)}</td><td class="time-cell">${date(job.created)}</td><td class="row-arrow" aria-hidden="true">›</td></tr>`,
        )
        .join("")}
    </tbody>
  </table>`;
}
function nodeCards(nodes, controls = false) {
  return nodes
    .map((node) => {
      const [name, address] = nodeNames[node.id] || [node.id, ""];
      let status = ["空闲", "online"];
      if (!node.online) status = ["离线", "offline"];
      else if (node.paused)
        status = [node.busy ? "处理中 · 暂停接单" : "暂停接单", "paused"];
      else if (node.busy) status = ["处理中", "running"];
      else if (node.profile.accepting === false)
        status = ["磁盘余量不足", "paused"];
      else if (!node.available) status = ["等待重试", "queued"];
      const profile = node.profile;
      const active = node.active_task;
      return /* HTML */ `<article class="node-card">
        <div class="node-top">
          <div class="node-name">
            <span class="node-icon" aria-hidden="true">▣</span>
            <div>
              <h3>${escapeHtml(name)}</h3>
              <p class="node-address">${escapeHtml(address)}</p>
            </div>
          </div>
          <span class="badge ${status[1]}">${status[0]}</span>
        </div>
        <div class="node-profile">
          <span
            >Indra<strong
              >${profile.cores ? `${profile.cores} 工作单元` : "待上报"}</strong
            ></span
          ><span
            >ScreenAI<strong
              >${profile.screenai_workers
                ? `${profile.screenai_workers} 进程`
                : "待上报"}</strong
            ></span
          >
        </div>
        <div class="node-work">
          ${active
            ? `<button class="button secondary small text-link" data-job="${escapeHtml(active.parent || active.id)}">${escapeHtml(active.filename || kinds[active.kind] || active.id.slice(0, 12))}</button>`
            : node.paused
              ? "暂停接收新任务"
              : node.available
                ? "可接收后续任务"
                : node.profile.accepting === false
                  ? `工作盘可用 ${bytes(node.profile.work_free_bytes)}`
                  : node.online
                    ? "等待后续调度"
                    : "等待节点连接"}
        </div>
        <div class="node-bottom">
          <span class="muted"
            >${node.updated
              ? `心跳 ${duration(Math.max(0, overview.server_time - node.updated))}前`
              : "尚无心跳记录"}</span
          >${controls
            ? `<button class="button secondary small" data-node="${escapeHtml(node.id)}" data-paused="${!node.paused}">${node.paused ? "恢复接单" : "暂停接单"}</button>`
            : ""}
        </div>
      </article>`;
    })
    .join("");
}
function renderOverview() {
  const counts = overview.counts;
  $("metrics").innerHTML = [
    ["待处理任务", counts.queued, "◷", ""],
    ["进行中任务", counts.running, "↗", ""],
    ["已完成任务", counts.done, "✓", "green"],
    ["失败任务", counts.failed, "!", "red"],
  ]
    .map(
      ([label, value, icon, color]) =>
        `<div class="metric"><div><p class="metric-label">${label}</p><span class="metric-value">${value}</span></div><span class="metric-marker ${color}" aria-hidden="true">${icon}</span></div>`,
    )
    .join("");
  $("overview-nodes").innerHTML = nodeCards(overview.health.nodes);
  $("node-list").innerHTML = nodeCards(overview.health.nodes, true);
  $("recent-tasks").innerHTML = taskTable(overview.recent);
  $("resource-table").innerHTML = /* HTML */ `<table>
    <thead>
      <tr>
        <th>节点</th>
        <th>Indra 工作单元</th>
        <th>ScreenAI 进程</th>
      </tr>
    </thead>
    <tbody>
      ${overview.health.nodes
        .map(
          (node) =>
            `<tr><td>${escapeHtml(nodeLabel(node.id))}</td><td>${node.profile.cores || "待上报"}</td><td>${node.profile.screenai_workers || "待上报"}</td></tr>`,
        )
        .join("")}
    </tbody>
  </table>`;
  const settings = overview.health.settings;
  const labels = [
    ["offline_seconds", "节点离线判定"],
    ["lease_seconds", "任务租约"],
    ["attempt_timeout", "单次执行上限"],
    ["queue_timeout", "排队上限"],
    ["document_timeout", "整书 / 任务组上限"],
    ["max_attempts", "每阶段最多尝试"],
    ["retry_delay", "自动重试起始间隔"],
  ];
  $("settings-table").innerHTML = labels
    .map(
      ([key, label]) =>
        `<div class="settings-row"><dt>${label}</dt><dd>${key === "max_attempts" ? settings[key] + " 次" : duration(settings[key])}</dd></div>`,
    )
    .join("");
  $("upload-limit").textContent =
    `支持 PDF 和包含 PDF 的 ZIP。每次请求上限 ${bytes(overview.upload_limit_bytes)}，ZIP 解压后的 PDF 总量采用相同上限。`;
  $("file-hint").textContent =
    `PDF / ZIP · 每次请求最多 ${bytes(overview.upload_limit_bytes)}`;
  const production = overview.production;
  const policy = production.policy;
  const policyRows = [
    ["单份 PDF 页数上限", `${policy.max_document_pages} 页`],
    ["单次提交文献上限", `${policy.max_documents_per_request} 份`],
    [
      "在途文献",
      `${production.pending.documents} / ${policy.max_pending_documents} 份`,
    ],
    [
      "在途页数",
      `${production.pending.pages} / ${policy.max_pending_pages} 页`,
    ],
    [
      "磁盘可用 / 预留",
      `${bytes(production.free_bytes)} / ${bytes(policy.min_free_bytes)}`,
    ],
    ["原件与最终成品", "长期保存"],
    ["成功中间批次", `${policy.intermediate_days} 天`],
    ["失败诊断", `${policy.diagnostic_days} 天`],
  ];
  $("production-policy").innerHTML = policyRows
    .map(
      ([label, value]) =>
        `<div class="settings-row"><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`,
    )
    .join("");
  const backup = production.backup;
  const backupRows = [
    ["最近备份", backup ? date(backup.created) : "待首次备份"],
    [
      "副本状态",
      backup?.replicated ? `已校验 · ${backup.replica_host}` : "待异机校验",
    ],
    ["备份大小", backup ? bytes(backup.bytes) : "—"],
    ["保留份数", `${policy.backup_copies} 份`],
    [
      "最近中间产物清理",
      production.cleanup ? date(production.cleanup.finished) : "待首次执行",
    ],
  ];
  if (backup && overview.server_time - backup.created > 36 * 3600)
    backupRows.push(["备份状态", "超过 36 小时未更新"]);
  $("backup-status").innerHTML = backupRows
    .map(
      ([label, value]) =>
        `<div class="settings-row"><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`,
    )
    .join("");
  $("last-refresh").textContent = `更新于 ${date(overview.server_time)}`;
}
async function refresh() {
  if (!authenticated) return;
  refreshController?.abort();
  const controller = new AbortController();
  refreshController = controller;
  try {
    const data = await api("/admin/overview", { signal: controller.signal });
    if (controller.signal.aborted) return;
    overview = data;
    renderOverview();
    if (currentPage === "tasks") {
      const query = new URLSearchParams({
        search: $("search").value.trim(),
        status: $("status-filter").value,
        limit: "20",
        offset: String(offset),
      });
      const result = await api("/admin/jobs?" + query, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (offset >= result.total && offset > 0) {
        offset = Math.max(0, offset - 20);
        return refresh();
      }
      $("task-table").innerHTML = taskTable(result.items);
      $("task-total").textContent = `${result.total} 个任务`;
      $("page-count").textContent = result.total
        ? `${offset + 1}–${Math.min(offset + 20, result.total)} / ${result.total}`
        : "0 个任务";
      $("previous-page").disabled = offset === 0;
      $("next-page").disabled = offset + 20 >= result.total;
    }
    $("connection").className = "connection online";
    $("connection").innerHTML = "<i></i>网关在线";
    $("page-error").hidden = true;
    if (selectedTask && $("detail-dialog").open) await loadDetail(selectedTask);
  } catch (error) {
    if (error.name === "AbortError" || !authenticated) return;
    $("connection").className = "connection error";
    $("connection").innerHTML = "<i></i>连接中断";
    $("page-error").textContent = "数据更新失败。" + error.message;
    $("page-error").hidden = false;
  }
}
function navigate() {
  const page = location.hash.slice(1) || "overview";
  currentPage = Object.hasOwn(titles, page) ? page : "overview";
  $("page-title").textContent = titles[currentPage];
  document.querySelectorAll("[data-view]").forEach((element) => {
    element.hidden = element.dataset.view !== currentPage;
  });
  document.querySelectorAll("[data-nav]").forEach((element) => {
    element.classList.toggle("active", element.dataset.nav === currentPage);
  });
  refresh();
}
async function loadDetail(id) {
  const generation = ++detailGeneration;
  const [job, artifacts] = await Promise.all([
    api("/jobs/" + encodeURIComponent(id)),
    api("/jobs/" + encodeURIComponent(id) + "/artifacts"),
  ]);
  if (
    generation !== detailGeneration ||
    selectedTask !== id ||
    !$("detail-dialog").open
  )
    return;
  $("detail-title").textContent = nameOf(job);
  const active = ["queued", "running"].includes(job.status);
  const actions =
    !job.parent && active
      ? `<button class="button danger small" data-operation="cancel" data-id="${job.id}">取消任务</button>`
      : !job.parent && ["failed", "cancelled"].includes(job.status)
        ? `<button class="button primary small" data-operation="retry" data-id="${job.id}">重试任务</button>`
        : "";
  const downloads = artifacts.items
    .filter((item) => item.size > 0)
    .map(
      (item) =>
        `<a class="button secondary small" href="${escapeHtml(item.url)}">${escapeHtml(item.label)} · ${bytes(item.size)}</a>`,
    );
  if (artifacts.input_url)
    downloads.unshift(
      `<a class="button secondary small" href="${escapeHtml(artifacts.input_url)}">原始 PDF</a>`,
    );
  if (artifacts.result_url)
    downloads.push(
      `<a class="button secondary small" href="${escapeHtml(artifacts.result_url)}">全部成果</a>`,
    );
  const ended = active
    ? overview?.server_time || Date.now() / 1000
    : job.updated;
  const meta = [
    ["任务编号", job.id],
    ["任务类型", kinds[job.kind] || job.kind],
    ["登记时间", date(job.created)],
    ["本次耗时", duration(ended - (job.retried_at || job.created))],
  ];
  if (job.details.page_count)
    meta.push(["文献页数", job.details.page_count + " 页"]);
  if (job.details.batch_pages)
    meta.push(["每批页数", job.details.batch_pages + " 页"]);
  $("detail-body").innerHTML =
    `${job.parent ? `<button class="button secondary small" data-job="${escapeHtml(job.parent)}">← 查看所属任务</button>` : ""}<div class="detail-summary">${badge(job.status)}<span class="muted">${escapeHtml(stage(job))}</span><div class="detail-actions">${actions}</div></div>${job.progress.total_pages ? `<div class="detail-progress">${progress(job)}</div>` : ""}<dl class="detail-meta">${meta.map(([key, value]) => `<div><dt>${key}</dt><dd${key === "任务编号" ? ' class="mono"' : ""}>${escapeHtml(value)}</dd></div>`).join("")}</dl>${downloads.length ? `<section class="detail-section"><h3>文件与成果</h3><div class="artifact-list">${downloads.join("")}</div></section>` : ""}${job.error ? `<section class="detail-section"><h3>故障信息</h3><pre class="error-detail">${escapeHtml(job.error)}</pre></section>` : ""}${job.children.length ? `<section class="detail-section"><h3>${job.kind === "group" ? "文献" : "处理阶段与批次"}</h3><div class="panel table-wrap"><table><thead><tr><th>阶段 / 范围</th><th>状态</th><th>节点</th><th>累计尝试</th><th></th></tr></thead><tbody>${job.children.map((child) => `<tr data-job="${escapeHtml(child.id)}" tabindex="0"><td>${escapeHtml(child.details.filename && child.kind === "book" ? child.details.filename : kinds[child.kind] || child.kind)}${child.details.count ? `<div class="muted">第 ${child.details.start + 1}–${child.details.start + child.details.count} 页</div>` : ""}</td><td>${badge(child.status)}</td><td>${escapeHtml(nodeLabel(child.node))}</td><td>${child.attempts}</td><td class="row-arrow">›</td></tr>`).join("")}</tbody></table></div></section>` : ""}${job.attempt_history.length ? `<section class="detail-section"><h3>执行记录</h3>${job.attempt_history.map((attempt) => `<div class="history-item"><div><strong>第 ${attempt.number} 次</strong><span>${escapeHtml(nodeLabel(attempt.node))}</span>${badge(attempt.status)}</div><span class="muted">${date(attempt.started)}${attempt.finished ? " → " + date(attempt.finished) : ""}</span>${attempt.error ? `<pre class="error-detail">${escapeHtml(attempt.error)}</pre>` : ""}</div>`).join("")}</section>` : ""}`;
  if (artifacts.expired_at) {
    const notice = document.createElement("p");
    notice.className = "muted";
    notice.textContent =
      "中间批次已按保存策略清理，原件与最终成品保存在所属文献任务中。";
    $("detail-body").prepend(notice);
  }
}
async function openTask(id) {
  selectedTask = id;
  $("detail-title").textContent = "正在读取任务";
  $("detail-body").replaceChildren();
  if (!$("detail-dialog").open) $("detail-dialog").showModal();
  try {
    await loadDetail(id);
  } catch (error) {
    toast(error.message);
  }
}
function confirmation(title, message, label) {
  $("confirm-title").textContent = title;
  $("confirm-copy").textContent = message;
  $("confirm-action").textContent = label;
  $("confirm-dialog").showModal();
  return new Promise((resolve) => {
    pendingConfirmation = resolve;
  });
}
async function taskOperation(operation, id) {
  if (
    operation === "cancel" &&
    !(await confirmation(
      "取消任务",
      "已完成批次将保留，正在处理的尝试将在下一次心跳时停止。",
      "取消任务",
    ))
  )
    return;
  try {
    await api(`/admin/jobs/${encodeURIComponent(id)}/${operation}`, {
      method: "POST",
      body: {},
    });
    toast(
      operation === "cancel"
        ? "取消请求已生效"
        : "任务已重新排队，已完成批次继续复用",
    );
    await refresh();
  } catch (error) {
    toast(error.message);
  }
}
function renderFiles() {
  $("selected-files").innerHTML = files
    .map(
      (entry, index) =>
        `<div class="selected-file"><div><strong>${escapeHtml(entry.file.name)}</strong><small>${bytes(entry.file.size)}${entry.id ? " · 已提交 " + entry.id.slice(0, 8) : ""}</small>${entry.started ? `<progress value="${entry.progress}" max="100" aria-label="文件上传进度"></progress>` : ""}${entry.error ? `<p class="form-error">${escapeHtml(entry.error)}</p>` : ""}</div>${!uploading && !entry.id ? `<button type="button" class="icon-button" data-remove="${index}" aria-label="移除 ${escapeHtml(entry.file.name)}">×</button>` : ""}</div>`,
    )
    .join("");
  $("file-picker").disabled = uploading;
  $("batch-pages").disabled = Boolean(uploadSettings);
  $("preferred-node").disabled = Boolean(uploadSettings);
  $("submit-files").disabled = uploading || !files.some((entry) => !entry.id);
  $("submit-files").textContent = uploading ? "正在提交…" : "提交任务";
  $("reset-files").disabled = uploading;
}
function addFiles(selected) {
  if (uploading || uploadSettings) return;
  for (const file of selected) {
    const key = Array.from(
      crypto.getRandomValues(new Uint8Array(16)),
      (value) => value.toString(16).padStart(2, "0"),
    ).join("");
    let error = "";
    if (!/\.(pdf|zip)$/i.test(file.name)) error = "请选择 PDF 或 ZIP 文件";
    else if (overview && file.size > overview.upload_limit_bytes)
      error = "文件超过 " + bytes(overview.upload_limit_bytes) + " 上传上限";
    files.push({
      file,
      key,
      progress: 0,
      error,
      invalid: Boolean(error),
      id: null,
      started: false,
    });
  }
  renderFiles();
}
function upload(entry) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const parameters = new URLSearchParams({
      batch_pages: String(uploadSettings.batch),
      node: uploadSettings.node,
    });
    xhr.open("POST", "/jobs?" + parameters);
    xhr.setRequestHeader("X-CSRF-Token", csrf);
    xhr.setRequestHeader("X-Filename", encodeURIComponent(entry.file.name));
    xhr.setRequestHeader("Idempotency-Key", entry.key);
    xhr.setRequestHeader(
      "Content-Type",
      /\.zip$/i.test(entry.file.name) ? "application/zip" : "application/pdf",
    );
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        entry.progress = Math.round((event.loaded / event.total) * 100);
        renderFiles();
      }
    };
    xhr.onerror = () => reject(new Error("上传连接中断，可以重试本次提交"));
    xhr.onload = () => {
      let response;
      try {
        response = JSON.parse(xhr.responseText);
      } catch {
        reject(new Error("网关返回了无效响应"));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(response);
      else {
        if (xhr.status === 401) showLogin("登录已过期，请重新登录");
        reject(new Error(response.error || "上传失败"));
      }
    };
    xhr.send(entry.file);
  });
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $("login-error").textContent = "";
  try {
    const result = await api("/admin/login", {
      method: "POST",
      body: { token: $("access-key").value },
      authRedirect: false,
    });
    csrf = result.csrf_token;
    authenticated = true;
    $("access-key").value = "";
    $("login").hidden = true;
    $("app").hidden = false;
    navigate();
  } catch (error) {
    $("login-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("logout").addEventListener("click", async () => {
  try {
    await api("/admin/logout", { method: "POST", body: {} });
    showLogin();
  } catch (error) {
    toast(error.message);
  }
});
$("refresh").addEventListener("click", refresh);
$("new-task").addEventListener("click", () => {
  renderFiles();
  $("upload-dialog").showModal();
});
$("file-picker").addEventListener("change", (event) =>
  addFiles(event.target.files),
);
$("reset-files").addEventListener("click", () => {
  files = [];
  uploadSettings = null;
  $("file-picker").value = "";
  $("upload-error").textContent = "";
  renderFiles();
});
$("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const pending = files.filter((entry) => !entry.id);
  if (!pending.length || uploading) return;
  if (pending.some((entry) => entry.invalid)) {
    $("upload-error").textContent = "请移除不符合条件的文件";
    return;
  }
  const batch = Number($("batch-pages").value);
  if (!Number.isInteger(batch) || batch < 1) {
    $("upload-error").textContent = "每批页数需要为正整数";
    return;
  }
  uploadSettings ||= { batch, node: $("preferred-node").value };
  uploading = true;
  $("upload-error").textContent = "";
  renderFiles();
  for (const entry of pending) {
    if (!authenticated) break;
    entry.started = true;
    entry.error = "";
    try {
      const result = await upload(entry);
      entry.id = result.id;
      entry.progress = 100;
    } catch (error) {
      entry.error = error.message;
    }
    renderFiles();
  }
  uploading = false;
  renderFiles();
  if (authenticated && files.every((entry) => entry.id)) {
    toast(`${files.length} 个任务已提交`);
    $("upload-dialog").close();
    files = [];
    uploadSettings = null;
    $("file-picker").value = "";
    location.hash = "tasks";
    await refresh();
  }
});
$("drop-zone").addEventListener("dragover", (event) => {
  event.preventDefault();
  $("drop-zone").classList.add("dragging");
});
$("drop-zone").addEventListener("dragleave", () =>
  $("drop-zone").classList.remove("dragging"),
);
$("drop-zone").addEventListener("drop", (event) => {
  event.preventDefault();
  $("drop-zone").classList.remove("dragging");
  addFiles(event.dataTransfer.files);
});
$("confirm-back").addEventListener("click", () => $("confirm-dialog").close());
$("confirm-action").addEventListener("click", () => {
  pendingConfirmation?.(true);
  pendingConfirmation = null;
  $("confirm-dialog").close();
});
$("confirm-dialog").addEventListener("close", () => {
  pendingConfirmation?.(false);
  pendingConfirmation = null;
});
$("detail-dialog").addEventListener("close", () => {
  selectedTask = null;
  detailGeneration++;
});
document.addEventListener("click", async (event) => {
  const close = event.target.closest("[data-close]");
  if (close) $(close.dataset.close).close();
  const remove = event.target.closest("[data-remove]");
  if (remove && !uploading) {
    files.splice(Number(remove.dataset.remove), 1);
    if (!files.length) uploadSettings = null;
    renderFiles();
  }
  const job = event.target.closest("[data-job]");
  if (job) openTask(job.dataset.job);
  const operation = event.target.closest("[data-operation]");
  if (operation)
    taskOperation(operation.dataset.operation, operation.dataset.id);
  const node = event.target.closest("[data-node]");
  if (node) {
    node.disabled = true;
    try {
      await api("/admin/nodes/" + encodeURIComponent(node.dataset.node), {
        method: "POST",
        body: { paused: node.dataset.paused === "true" },
      });
      toast("节点接单设置已更新");
      await refresh();
    } catch (error) {
      toast(error.message);
      node.disabled = false;
    }
  }
});
document.addEventListener("keydown", (event) => {
  const row = event.target.closest("tr[data-job]");
  if (row && event.key === "Enter") openTask(row.dataset.job);
});
let searchTimer;
$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    offset = 0;
    refresh();
  }, 250);
});
$("status-filter").addEventListener("change", () => {
  offset = 0;
  refresh();
});
$("previous-page").addEventListener("click", () => {
  offset = Math.max(0, offset - 20);
  refresh();
});
$("next-page").addEventListener("click", () => {
  offset += 20;
  refresh();
});
window.addEventListener("hashchange", navigate);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
setInterval(() => {
  if (!document.hidden) refresh();
}, 5000);

async function start() {
  try {
    const session = await api("/admin/session", { authRedirect: false });
    csrf = session.csrf_token;
    authenticated = true;
    $("boot").hidden = true;
    $("app").hidden = false;
    navigate();
  } catch (error) {
    showLogin(error.status === 401 ? "" : "网关连接失败，请稍后重试");
  }
}
start();
