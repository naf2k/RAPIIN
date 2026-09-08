/* BERESIN Supervisor pages - shared logic bound by body[data-page]. */
(function () {
  "use strict";

  function fmtTime(iso) {
    if (!iso) return "-";
    var d = new Date(iso);
    var now = new Date();
    var sameDay = d.toDateString() === now.toDateString();
    return sameDay
      ? d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })
      : d.toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  function statusLabel(raw) {
    var map = {
      ONLINE: ["online", "Online"],
      OFFLINE: ["offline", "Offline"],
      PENDING: ["neutral", "Antre"],
      PLANNING: ["warning", "Merencanakan"],
      WAITING_APPROVAL: ["warning", "Menunggu persetujuan"],
      RUNNING: ["running", "Berjalan"],
      VERIFYING: ["warning", "Memverifikasi"],
      COMPLETED: ["completed", "Selesai"],
      FAILED: ["failed", "Gagal"],
      CANCELLED: ["neutral", "Dibatalkan"],
      APPROVED: ["completed", "Disetujui"],
      REJECTED: ["failed", "Ditolak"],
      USER: ["neutral", "User"],
      SUPERVISOR: ["neutral", "Supervisor"],
    };
    var m = map[raw] || ["neutral", raw || "-"];
    return m;
  }

  function statusBadge(raw) {
    var m = statusLabel(raw);
    var span = document.createElement("span");
    span.className = "status status--" + m[0];
    var icon = document.createElement("span");
    icon.className = "status-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = m[0] === "offline" || m[0] === "failed" ? "○" : m[0] === "completed" ? "✓" : "●";
    span.appendChild(icon);
    span.appendChild(document.createTextNode(m[1]));
    return span;
  }

  function setText(id, val) {
    var el = BERESIN.el(id);
    if (el) el.textContent = val === null || val === undefined ? "-" : val;
  }

  function clearList(id, emptyMsg) {
    var list = BERESIN.el(id);
    if (!list) return;
    list.innerHTML = "";
    if (emptyMsg) {
      var p = document.createElement("p");
      p.className = "history-empty";
      p.textContent = emptyMsg;
      list.appendChild(p);
    }
  }

  async function loadOverview() {
    var data = await BERESIN.api("GET", "/supervisor/overview");
    setText("metric-users", data.active_users);
    setText("metric-running", data.running_tasks);
    setText("metric-success", data.success_rate === null || data.success_rate === undefined ? "-" : data.success_rate + "%");
    setText("metric-status", data.status === "SEHAT" ? "Sehat" : "Perlu perhatian");
    setText("metric-status-note", data.status === "SEHAT" ? "Tidak ada gangguan" : data.failed_tasks + " task gagal");
    var statusEl = BERESIN.el("system-status");
    if (statusEl) statusEl.textContent = data.status === "SEHAT" ? "Sistem berjalan normal" : "Ada yang perlu diperhatikan";

    // Needs attention
    clearList("attention-list", "Tidak ada hal yang perlu perhatian.");
    var att = BERESIN.el("attention-list");
    (data.attention || []).forEach(function (item) {
      var a = document.createElement("a");
      a.className = "attention-item";
      a.href = item.link || "#";
      var icon = document.createElement("span");
      icon.className = "item-icon " + (item.type === "task_failed" ? "item-icon--danger" : "item-icon--warning");
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = item.type === "device_offline" ? "○" : "!";
      var copy = document.createElement("span");
      copy.className = "item-copy";
      var t = document.createElement("strong");
      t.textContent = item.title;
      var d = document.createElement("span");
      d.textContent = item.detail || "";
      copy.appendChild(t);
      copy.appendChild(d);
      a.appendChild(icon);
      a.appendChild(copy);
      att.appendChild(a);
    });

    // Recent activity
    clearList("activity-list", "Belum ada aktivitas.");
    var act = BERESIN.el("activity-list");
    (data.recent_activity || []).forEach(function (item) {
      var a = document.createElement("a");
      a.className = "activity-item";
      a.href = "activity.html";
      var icon = document.createElement("span");
      icon.className = "item-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = item.result === "FAILED" ? "!" : "✓";
      var copy = document.createElement("span");
      copy.className = "item-copy";
      var t = document.createElement("strong");
      t.textContent = item.actor + " " + item.action;
      var d = document.createElement("span");
      d.textContent = item.resource || "";
      var time = document.createElement("small");
      time.textContent = fmtTime(item.timestamp);
      copy.appendChild(t);
      copy.appendChild(d);
      copy.appendChild(time);
      a.appendChild(icon);
      a.appendChild(copy);
      act.appendChild(a);
    });
  }

  async function loadTasks() {
    var listEl = BERESIN.el("tasks-table-body");
    if (!listEl) return;
    var params = new URLSearchParams();
    var statusFilter = BERESIN.el("task-status-filter");
    var searchInput = BERESIN.el("task-search");
    var status = statusFilter ? statusFilter.getAttribute("data-status") : "";
    if (status && status !== "ALL") params.set("status", status);
    if (searchInput && searchInput.value.trim()) params.set("q", searchInput.value.trim());
    var tasks = await BERESIN.api("GET", "/supervisor/tasks?" + params.toString());
    listEl.innerHTML = "";
    if (!tasks.length) {
      var row = document.createElement("tr");
      var cell = document.createElement("td");
      cell.colSpan = 6;
      cell.textContent = "Belum ada task.";
      row.appendChild(cell);
      listEl.appendChild(row);
      return;
    }
    tasks.forEach(function (t) {
      var tr = document.createElement("tr");
      var cells = [
        { label: "Pengguna", html: "<strong>User #" + t.user_id + "</strong>" },
        { label: "Task", html: '<a href="task-detail.html?id=' + t.id + '">' + BERESIN.esc(t.type) + "</a>" },
        { label: "Perangkat", text: t.device_id ? "Device #" + t.device_id : "-" },
        { label: "Status", badge: t.status },
        { label: "Progress", text: t.status === "COMPLETED" ? "100%" : (t.progress || 0) + "%" },
        { label: "Waktu", text: fmtTime(t.created_at) },
      ];
      cells.forEach(function (c) {
        var td = document.createElement("td");
        td.setAttribute("data-label", c.label);
        if (c.badge) td.appendChild(statusBadge(c.badge));
        else if (c.html) td.innerHTML = c.html;
        else td.textContent = c.text || "-";
        tr.appendChild(td);
      });
      listEl.appendChild(tr);
    });
  }

  async function loadTaskDetail() {
    var params = new URLSearchParams(window.location.search);
    var id = params.get("id");
    var box = BERESIN.el("task-detail");
    if (!box) return;
    if (!id) { box.innerHTML = '<p class="history-empty">Task tidak ditemukan.</p>'; return; }
    var t = await BERESIN.api("GET", "/supervisor/tasks/" + id);
    setText("detail-title", t.type);
    setText("detail-user", "User #" + t.user_id);
    setText("detail-device", t.device_id ? "Device #" + t.device_id : "-");
    setText("detail-status", statusLabel(t.status)[1]);
    setText("detail-progress", Math.round((t.progress || 0)) + "%");
    setText("detail-started", fmtTime(t.started_at || t.created_at));
    setText("detail-error", t.error || "Tidak ada error.");
    var badge = BERESIN.el("detail-status-badge");
    if (badge) {
      badge.innerHTML = "";
      badge.appendChild(statusBadge(t.status));
    }
    // activity timeline
    var timeline = BERESIN.el("detail-timeline");
    if (timeline) {
      timeline.innerHTML = "";
      var acts = t.activity || [];
      if (!acts.length) {
        timeline.innerHTML = '<p class="history-empty">Belum ada aktivitas tercatat.</p>';
      } else {
        acts.slice(0, 15).forEach(function (a) {
          var div = document.createElement("div");
          div.className = "timeline-item";
          var time = document.createElement("time");
          time.className = "timeline-time";
          time.textContent = fmtTime(a.timestamp);
          var copy = document.createElement("div");
          copy.className = "timeline-copy";
          var h = document.createElement("h3");
          h.textContent = (a.actor || "system") + " - " + a.action;
          var p = document.createElement("p");
          p.textContent = a.resource || "";
          if (a.result === "FAILED") p.textContent += " (gagal)";
          copy.appendChild(h);
          copy.appendChild(p);
          div.appendChild(time);
          div.appendChild(copy);
          timeline.appendChild(div);
        });
      }
    }
  }

  async function loadEmployees() {
    var tbody = BERESIN.el("employees-table-body");
    if (!tbody) return;
    var params = new URLSearchParams();
    var searchInput = BERESIN.el("employee-search");
    if (searchInput && searchInput.value.trim()) params.set("q", searchInput.value.trim());
    var emps = await BERESIN.api("GET", "/supervisor/employees?" + params.toString());
    tbody.innerHTML = "";
    if (!emps.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = "Belum ada employee.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    emps.forEach(function (e) {
      var tr = document.createElement("tr");
      var cells = [
        { label: "Employee", html: '<a href="employee-detail.html?id=' + e.user_id + '"><strong>' + BERESIN.esc(e.name || "User #" + e.user_id) + "</strong></a>" },
        { label: "Device", text: e.device_name || "-" },
        { label: "Koneksi", badge: e.device_status || "OFFLINE" },
        { label: "Tugas aktif", text: e.active_tasks !== undefined ? String(e.active_tasks) : "-" },
        { label: "Aktivitas", text: fmtTime(e.last_heartbeat_at) },
      ];
      cells.forEach(function (c) {
        var td = document.createElement("td");
        td.setAttribute("data-label", c.label);
        if (c.badge) td.appendChild(statusBadge(c.badge));
        else if (c.html) td.innerHTML = c.html;
        else td.textContent = c.text || "-";
        tr.appendChild(td);
      });
      // Action cell: enable/disable account.
      var actionTd = document.createElement("td");
      actionTd.setAttribute("data-label", "Aksi");
      var toggle = document.createElement("button");
      toggle.className = "button button--secondary";
      toggle.type = "button";
      toggle.style.minHeight = "30px";
      toggle.style.padding = "5px 10px";
      toggle.style.fontSize = "11px";
      toggle.textContent = e.is_active ? "Nonaktifkan" : "Aktifkan";
      toggle.addEventListener("click", function () {
        setEmployeeState(e.user_id, !e.is_active, toggle);
      });
      actionTd.appendChild(toggle);
      tr.appendChild(actionTd);
      tbody.appendChild(tr);
    });
  }

  async function setEmployeeState(userId, isActive, btn) {
    try {
      await BERESIN.api("PATCH", "/supervisor/employees/" + userId + "/state", { is_active: isActive });
      btn.textContent = isActive ? "Nonaktifkan" : "Aktifkan";
      BERESIN.showToast(isActive ? "Akun diaktifkan." : "Akun dinonaktifkan.", "success");
      loadEmployees().catch(function (e) { BERESIN.showError(e.message); });
    } catch (err) {
      BERESIN.showError(err.message);
    }
  }

  function wireEmployeePanel() {
    var addBtn = BERESIN.el("btn-add-employee");
    var panel = BERESIN.el("add-employee-panel");
    var cancelBtn = BERESIN.el("btn-cancel-add");
    if (!addBtn || !panel) return;
    addBtn.addEventListener("click", function () { panel.hidden = !panel.hidden; });
    cancelBtn.addEventListener("click", function () { panel.hidden = true; });
    var form = BERESIN.el("add-employee-form");
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var errBox = BERESIN.el("add-employee-error");
      errBox.hidden = true;
      try {
        await BERESIN.api("POST", "/supervisor/employees", {
          name: BERESIN.el("new-emp-name").value.trim(),
          email: BERESIN.el("new-emp-email").value.trim(),
          password: BERESIN.el("new-emp-password").value,
        });
        form.reset();
        panel.hidden = true;
        BERESIN.showToast("Akun employee dibuat.", "success");
        loadEmployees().catch(function (err2) { BERESIN.showError(err2.message); });
      } catch (err) {
        errBox.textContent = err.message;
        errBox.hidden = false;
      }
    });
  }

  async function loadEmployeeDetail() {
    var params = new URLSearchParams(window.location.search);
    var id = params.get("id");
    if (!id) { BERESIN.showError("Employee tidak ditemukan."); return; }
    var data = await BERESIN.api("GET", "/supervisor/employees/" + id);
    setText("emp-title", data.name || "Employee");
    setText("emp-email", data.email || "-");
    setText("emp-device", data.device_name || "-");
    setText("emp-os", data.os || "-");
    setText("emp-agent", data.agent_version || "-");
    setText("emp-heartbeat", fmtTime(data.last_heartbeat_at));
    var badge = BERESIN.el("emp-status-badge");
    if (badge) {
      badge.innerHTML = "";
      badge.appendChild(statusBadge(data.device_status || "OFFLINE"));
    }
    var taskBox = BERESIN.el("emp-tasks");
    if (taskBox) {
      taskBox.innerHTML = "";
      var tasks = data.tasks || [];
      if (!tasks.length) taskBox.innerHTML = '<p class="history-empty">Tidak ada task untuk employee ini.</p>';
      tasks.slice(0, 8).forEach(function (t) {
        var a = document.createElement("a");
        a.className = "attention-item";
        a.href = "task-detail.html?id=" + t.id;
        var copy = document.createElement("span");
        copy.className = "item-copy";
        var strong = document.createElement("strong");
        strong.textContent = t.type;
        var small = document.createElement("small");
        small.textContent = statusLabel(t.status)[1] + " · " + Math.round((t.progress || 0)) + "%";
        copy.appendChild(strong);
        copy.appendChild(small);
        a.appendChild(copy);
        taskBox.appendChild(a);
      });
    }
  }

  async function loadApprovals() {
    var box = BERESIN.el("approval-list");
    if (!box) return;
    var approvals = await BERESIN.api("GET", "/supervisor/approvals");
    box.innerHTML = "";
    if (!approvals.length) {
      box.innerHTML = '<div class="state state--empty"><h2>Tidak ada permintaan persetujuan</h2><p>Permintaan yang membutuhkan keputusan supervisor akan muncul di sini.</p></div>';
      return;
    }
    var countEl = BERESIN.el("approval-count");
    if (countEl) countEl.textContent = approvals.length + " menunggu";
    approvals.forEach(function (ap) {
      var article = document.createElement("article");
      article.className = "approval-item";
      var icon = document.createElement("span");
      icon.className = "item-icon " + (ap.risk && ap.risk.indexOf("Hapus") >= 0 ? "item-icon--danger" : "item-icon--warning");
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = "!";
      var copy = document.createElement("span");
      copy.className = "item-copy";
      var who = document.createElement("strong");
      who.textContent = "User #" + ap.user_id + " (" + ap.kind + ")";
      var action = document.createElement("span");
      action.textContent = ap.action || "-";
      var meta = document.createElement("small");
      meta.textContent = (ap.risk || "") + " · Diminta " + fmtTime(ap.created_at);
      copy.appendChild(who);
      copy.appendChild(action);
      copy.appendChild(meta);
      var btnWrap = document.createElement("span");
      btnWrap.className = "item-action";
      var btn = document.createElement("a");
      btn.className = "button button--secondary";
      btn.href = "approval-detail.html?id=" + ap.id;
      btn.textContent = "Tinjau";
      btnWrap.appendChild(btn);
      article.appendChild(icon);
      article.appendChild(copy);
      article.appendChild(btnWrap);
      box.appendChild(article);
    });
  }

  async function loadApprovalDetail() {
    var params = new URLSearchParams(window.location.search);
    var id = params.get("id");
    if (!id) { BERESIN.showError("Approval tidak ditemukan."); return; }
    var ap = await BERESIN.api("GET", "/supervisor/approvals");
    var item = ap.find(function (a) { return String(a.id) === String(id); });
    if (!item) { BERESIN.showError("Approval tidak ditemukan."); return; }
    setText("ap-user", "User #" + item.user_id);
    setText("ap-action", item.action || "-");
    setText("ap-scope", item.scope || "-");
    setText("ap-risk", item.risk || "-");
    setText("ap-time", fmtTime(item.created_at));
    setText("ap-kind", item.kind === "SUPERVISOR" ? "Persetujuan supervisor" : "Persetujuan pengguna");
    var actionsBox = BERESIN.el("ap-actions");
    if (actionsBox) {
      actionsBox.innerHTML = "";
      var reject = document.createElement("button");
      reject.className = "button button--danger";
      reject.textContent = "Tolak";
      reject.addEventListener("click", function () { respond(id, "REJECTED"); });
      var approve = document.createElement("button");
      approve.className = "button button--primary";
      approve.textContent = "Setujui";
      approve.addEventListener("click", function () { respond(id, "APPROVED"); });
      actionsBox.appendChild(reject);
      actionsBox.appendChild(approve);
    }
  }

  async function respond(id, decision) {
    try {
      await BERESIN.api("POST", "/supervisor/approvals/" + id + "/respond", { decision: decision });
      BERESIN.showToast(decision === "APPROVED" ? "Persetujuan diberikan." : "Permintaan ditolak.", "success");
      setTimeout(function () { window.location.href = "approvals.html"; }, 800);
    } catch (err) {
      BERESIN.showError(err.message);
    }
  }

  async function loadActivity() {
    var box = BERESIN.el("activity-timeline");
    if (!box) return;
    var rows = await BERESIN.api("GET", "/supervisor/activity");
    box.innerHTML = "";
    if (!rows.length) {
      box.innerHTML = '<p class="history-empty">Belum ada aktivitas tercatat.</p>';
      return;
    }
    rows.slice(0, 50).forEach(function (a) {
      var div = document.createElement("div");
      div.className = "timeline-item";
      var time = document.createElement("time");
      time.className = "timeline-time";
      time.textContent = fmtTime(a.timestamp);
      var copy = document.createElement("div");
      copy.className = "timeline-copy";
      var h = document.createElement("h3");
      h.textContent = (a.actor || "system") + " " + a.action;
      var p = document.createElement("p");
      p.textContent = a.resource || "";
      if (a.error) p.textContent += " - " + a.error;
      copy.appendChild(h);
      copy.appendChild(p);
      div.appendChild(time);
      div.appendChild(copy);
      box.appendChild(div);
    });
  }

  async function loadSupervisorChat() {
    var form = BERESIN.el("sup-chat-form");
    var messages = BERESIN.el("sup-chat-messages");
    if (!form || !messages) return;
    var list = BERESIN.el("sup-prompt-list");
    if (list) {
      list.querySelectorAll("[data-question]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var input = BERESIN.el("sup-chat-input");
          input.value = btn.getAttribute("data-question");
          form.dispatchEvent(new Event("submit"));
        });
      });
    }
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      var input = BERESIN.el("sup-chat-input");
      var text = input.value.trim();
      if (!text) return;
      append(messages, "user", text);
      input.value = "";
      var typing = append(messages, "assistant", "Sedang memproses...");
      try {
        var data = await BERESIN.api("POST", "/supervisor/chat", { message: text });
        typing.textContent = data.reply || "";
      } catch (err) {
        typing.textContent = "Maaf, saya belum dapat menjawab: " + err.message;
      }
      messages.scrollTop = messages.scrollHeight;
    });
  }

  function append(container, role, text) {
    var div = document.createElement("div");
    div.className = "message message--" + (role === "user" ? "user" : "assistant");
    var p = document.createElement("p");
    p.textContent = text;
    div.appendChild(p);
    container.appendChild(div);
    return p;
  }

  async function loadSupervisorSettings() {
    // Profile
    var user = BERESIN.getUser();
    if (BERESIN.el("account-name")) BERESIN.el("account-name").textContent = user && user.name ? user.name : "Supervisor";
    if (BERESIN.el("avatar-letter")) BERESIN.el("avatar-letter").textContent = (user && user.name ? user.name : "S").charAt(0).toUpperCase();

    var profile = {};
    try {
      profile = await BERESIN.api("GET", "/supervisor/profile");
      if (BERESIN.el("profile-name")) BERESIN.el("profile-name").value = profile.name || "";
      if (BERESIN.el("profile-email")) BERESIN.el("profile-email").value = profile.email || "";
    } catch (err) {
      BERESIN.showError(err.message);
    }

    var form = BERESIN.el("profile-form");
    if (form) {
      form.addEventListener("submit", async function (e) {
        e.preventDefault();
        var body = { name: BERESIN.el("profile-name").value.trim() };
        var pw = BERESIN.el("profile-password").value;
        if (pw) body.password = pw;
        try {
          await BERESIN.api("PATCH", "/supervisor/profile", body);
          BERESIN.showToast("Profil diperbarui.", "success");
          var u = BERESIN.getUser();
          if (u && body.name) {
            u.name = body.name;
            BERESIN.setSession(null, u);
            if (BERESIN.el("account-name")) BERESIN.el("account-name").textContent = body.name;
          }
          BERESIN.el("profile-password").value = "";
        } catch (err) {
          BERESIN.showError(err.message);
        }
      });
    }

    // Supervisor accounts list
    var box = BERESIN.el("accounts-box");
    if (box) {
      try {
        var data = await BERESIN.api("GET", "/supervisor/accounts");
        box.innerHTML = "";
        data.accounts.forEach(function (a) {
          var row = document.createElement("div");
          row.className = "setting-row";
          var copy = document.createElement("span");
          copy.className = "setting-copy";
          var strong = document.createElement("strong");
          strong.textContent = a.name + (a.id === profile.id ? " (Anda)" : "");
          var small = document.createElement("small");
          small.textContent = a.email;
          copy.appendChild(strong);
          copy.appendChild(small);
          row.appendChild(copy);
          row.appendChild(document.createTextNode(a.is_active ? "Aktif" : "Nonaktif"));
          box.appendChild(row);
        });
        var createPanel = BERESIN.el("supervisor-create-panel");
        if (createPanel) createPanel.hidden = data.count >= data.max;
      } catch (err) {
        BERESIN.showError(err.message);
      }
    }
    var supervisorForm = BERESIN.el("supervisor-create-form");
    if (supervisorForm) supervisorForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      try {
        await BERESIN.api("POST", "/supervisor/accounts", {
          name: BERESIN.el("supervisor-name").value.trim(), email: BERESIN.el("supervisor-email").value.trim(), password: BERESIN.el("supervisor-password").value,
        });
        BERESIN.showToast("Supervisor kedua dibuat.", "success");
        supervisorForm.reset();
        window.location.reload();
      } catch (err) { BERESIN.showError(err.message); }
    });
    await loadPolicies();
  }

  async function loadPolicies() {
    var table = BERESIN.el("policy-table");
    if (!table) return;
    var policies = await BERESIN.api("GET", "/supervisor/policies");
    table.innerHTML = "";
    policies.forEach(function (policy) {
      var row = document.createElement("tr");
      var tool = document.createElement("td"); tool.textContent = policy.tool_name;
      var kindCell = document.createElement("td");
      var select = document.createElement("select"); select.className = "input";
      ["AUTO", "USER", "SUPERVISOR"].forEach(function (kind) {
        var option = document.createElement("option"); option.value = kind;
        option.textContent = kind === "AUTO" ? "Otomatis" : kind === "USER" ? "User" : "Supervisor";
        option.selected = kind === policy.approval_kind;
        if (kind === "AUTO" && ["file_delete", "bulk_delete", "batch_executor"].indexOf(policy.tool_name) >= 0) option.disabled = true;
        select.appendChild(option);
      });
      kindCell.appendChild(select);
      var limitCell = document.createElement("td");
      var limit = document.createElement("input"); limit.className = "input"; limit.type = "number"; limit.min = "1"; limit.max = "10000"; limit.value = policy.bulk_threshold || 20;
      limitCell.appendChild(limit);
      var action = document.createElement("td");
      var save = document.createElement("button"); save.className = "button button--secondary"; save.textContent = "Simpan";
      save.addEventListener("click", async function () {
        try {
          await BERESIN.api("PUT", "/supervisor/policies/" + policy.tool_name, {approval_kind: select.value, bulk_threshold: Number(limit.value)});
          BERESIN.showToast("Kebijakan " + policy.tool_name + " disimpan.", "success");
        } catch (err) { BERESIN.showError(err.message); }
      });
      action.appendChild(save);
      [tool, kindCell, limitCell, action].forEach(function (cell) { row.appendChild(cell); });
      table.appendChild(row);
    });
  }

  function setAccountName() {
    var user = BERESIN.getUser();
    var el = BERESIN.el("account-name");
    if (el && user) el.textContent = user.name || "Supervisor";
  }

  function wirePageControls() {
    wireEmployeePanel();
    // Task search box (debounced)
    var taskSearch = BERESIN.el("task-search");
    if (taskSearch) {
      var timer = null;
      taskSearch.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          var page = document.body.getAttribute("data-page");
          if (page === "tasks") loadTasks().catch(function (e) { BERESIN.showError(e.message); });
        }, 350);
      });
    }
    // Task status filter buttons
    var filterRow = BERESIN.el("task-status-filter-row");
    if (filterRow) {
      filterRow.querySelectorAll("[data-status]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          filterRow.querySelectorAll("[data-status]").forEach(function (b) { b.classList.remove("is-active"); });
          btn.classList.add("is-active");
          BERESIN.el("task-status-filter").setAttribute("data-status", btn.getAttribute("data-status"));
          loadTasks().catch(function (e) { BERESIN.showError(e.message); });
        });
      });
    }
    // Employee search box
    var empSearch = BERESIN.el("employee-search");
    if (empSearch) {
      var empTimer = null;
      empSearch.addEventListener("input", function () {
        clearTimeout(empTimer);
        empTimer = setTimeout(function () {
          loadEmployees().catch(function (e) { BERESIN.showError(e.message); });
        }, 350);
      });
    }
  }

  function boot() {
    setAccountName();
    wirePageControls();
    var page = document.body.getAttribute("data-page");
    var runners = {
      overview: loadOverview,
      tasks: loadTasks,
      taskDetail: loadTaskDetail,
      employees: loadEmployees,
      employeeDetail: loadEmployeeDetail,
      approvals: loadApprovals,
      approvalDetail: loadApprovalDetail,
      activity: loadActivity,
      chat: loadSupervisorChat,
      settings: loadSupervisorSettings,
    };
    var fn = runners[page];
    if (fn) {
      fn().catch(function (err) {
        BERESIN.showError(err.message);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
