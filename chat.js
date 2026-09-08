/* BERESIN User Chat - conversation logic against the User API. */
(function () {
  "use strict";

  var state = {
    conversations: [],
    activeId: null,
    activeTitle: null,
    sending: false,
    streamingDraft: null,
    currentTaskId: null,
    devices: [],
    selectedDeviceId: null,
  };

  var els = {};
  var emptyTemplate = null;

  function qs(sel) { return document.querySelector(sel); }

  function init() {
    els.historyList = BERESIN.el("history-list");
    els.chatMessages = BERESIN.el("chat-messages");
    els.chatComposer = BERESIN.el("chat-composer");
    els.emptyState = BERESIN.el("empty-state");
    els.composer = BERESIN.el("composer");
    els.activeComposer = BERESIN.el("active-composer");
    els.message = BERESIN.el("message");
    els.activeMessage = BERESIN.el("active-message");
    els.newChatBtn = BERESIN.el("new-chat-btn");
    els.targetDevice = BERESIN.el("target-device");
    els.activeTargetDevice = BERESIN.el("active-target-device");

    // Populate account info.
    var user = BERESIN.getUser();
    if (user) {
      if (BERESIN.el("account-name")) BERESIN.el("account-name").textContent = user.name || "Pengguna";
      if (BERESIN.el("avatar-letter")) BERESIN.el("avatar-letter").textContent = (user.name || "A").charAt(0).toUpperCase();
    }

    // Capture the empty state before we might hide it.
    emptyTemplate = els.emptyState.cloneNode(true);

    els.newChatBtn.addEventListener("click", startNewChat);
    els.composer.addEventListener("submit", onSubmitEmpty);
    els.activeComposer.addEventListener("submit", onSubmitActive);
    [els.targetDevice, els.activeTargetDevice].forEach(function (select) {
      select.addEventListener("change", function () {
        state.selectedDeviceId = select.value ? Number(select.value) : null;
        syncDevicePickers();
      });
    });

    // Prompt chips fill and submit the empty composer.
    document.querySelectorAll(".prompt-chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        els.message.value = chip.getAttribute("data-prompt") || chip.textContent.trim();
        els.composer.dispatchEvent(new Event("submit"));
      });
    });

    autoResize(els.message);
    autoResize(els.activeMessage);
    els.message.addEventListener("input", function () { autoResize(els.message); });
    els.activeMessage.addEventListener("input", function () { autoResize(els.activeMessage); });

    loadDevices();
    loadConversations();
  }

  async function loadDevices() {
    try {
      state.devices = await BERESIN.api("GET", "/user/devices");
      var online = state.devices.filter(function (device) { return device.status === "ONLINE"; });
      if (online.length === 1) state.selectedDeviceId = online[0].id;
      if (state.selectedDeviceId && !online.some(function (device) { return device.id === state.selectedDeviceId; })) {
        state.selectedDeviceId = null;
      }
      syncDevicePickers();
    } catch (err) {
      state.devices = [];
      syncDevicePickers();
      BERESIN.showError("Daftar perangkat gagal dimuat. " + err.message);
    }
  }

  function syncDevicePickers() {
    [els.targetDevice, els.activeTargetDevice].forEach(function (select) {
      select.innerHTML = "";
      var online = state.devices.filter(function (device) { return device.status === "ONLINE"; });
      var prompt = document.createElement("option");
      prompt.value = "";
      prompt.textContent = online.length ? "Pilih perangkat" : "Tidak ada perangkat online";
      select.appendChild(prompt);
      state.devices.forEach(function (device) {
        var option = document.createElement("option");
        option.value = device.id;
        option.disabled = device.status !== "ONLINE";
        option.textContent = device.device_name + (device.status === "ONLINE" ? " · Online" : " · Offline");
        select.appendChild(option);
      });
      select.value = state.selectedDeviceId ? String(state.selectedDeviceId) : "";
      select.disabled = !state.devices.length;
    });
  }

  function autoResize(t) {
    if (!t) return;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 160) + "px";
  }

  function formatTime(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    var now = new Date();
    var sameDay = d.toDateString() === now.toDateString();
    var opts = sameDay ? { hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" };
    return d.toLocaleString("id-ID", opts);
  }

  async function loadConversations() {
    try {
      var convs = await BERESIN.api("GET", "/user/conversations");
      state.conversations = convs;
      renderHistory();

      // Resume most recent conversation if present.
      if (convs.length > 0) {
        openConversation(convs[0].id);
      }
    } catch (err) {
      renderHistory();
      BERESIN.showError(err.message);
    }
  }

  function renderHistory() {
    els.historyList.innerHTML = "";
    if (!state.conversations.length) {
      var empty = document.createElement("p");
      empty.className = "history-empty";
      empty.textContent = "Belum ada percakapan.";
      els.historyList.appendChild(empty);
      return;
    }
    state.conversations.forEach(function (conv) {
      var a = document.createElement("a");
      a.className = "history-item" + (conv.id === state.activeId ? " is-active" : "");
      a.href = "#main-content";
      var copy = document.createElement("span");
      copy.className = "history-copy";
      var title = document.createElement("span");
      title.textContent = conv.title || "Percakapan";
      var time = document.createElement("small");
      time.textContent = formatTime(conv.updated_at);
      copy.appendChild(title);
      copy.appendChild(time);
      a.appendChild(copy);
      a.addEventListener("click", function (e) {
        e.preventDefault();
        openConversation(conv.id);
      });
      els.historyList.appendChild(a);
    });
  }

  async function startNewChat() {
    try {
      var data = await BERESIN.api("POST", "/user/conversations", { title: "Percakapan baru" });
      var conv = { id: data.conversation_id, title: data.title, updated_at: new Date().toISOString() };
      state.conversations.unshift(conv);
      state.activeId = conv.id;
      state.activeTitle = conv.title;
      showEmptyState();
      renderHistory();
    } catch (err) {
      BERESIN.showError(err.message);
    }
  }

  async function openConversation(id) {
    state.activeId = id;
    renderHistory();
    els.chatMessages.innerHTML = "";
    try {
      var messages = await BERESIN.api("GET", "/user/conversations/" + id + "/messages");
      var conv = state.conversations.find(function (c) { return c.id === id; });
      state.activeTitle = conv ? conv.title : "Percakapan";

      if (!messages.length) {
        showEmptyState();
        return;
      }
      showChatArea();
      messages.forEach(function (m) { appendMessage(m.role, m.content); });
      scrollToBottom();
    } catch (err) {
      BERESIN.showError(err.message);
    }
  }

  function showEmptyState() {
    els.emptyState.hidden = false;
    els.chatMessages.hidden = true;
    els.chatComposer.hidden = true;
    els.message.focus();
  }

  function showChatArea() {
    els.emptyState.hidden = true;
    els.chatMessages.hidden = false;
    els.chatComposer.hidden = false;
  }

  function appendMessage(role, content) {
    var div = document.createElement("div");
    div.className = "message message--" + (role === "user" ? "user" : "assistant");
    var p = document.createElement("p");
    p.textContent = content || "";
    div.appendChild(p);
    els.chatMessages.appendChild(div);
    return div;
  }

  function appendTyping() {
    var div = document.createElement("div");
    div.className = "agent-activity agent-activity--progress";
    div.id = "typing-indicator";
    var dot = document.createElement("span");
    dot.className = "status-dot";
    dot.setAttribute("aria-hidden", "true");
    var span = document.createElement("span");
    span.className = "typing-text";
    span.textContent = "BERESIN sedang memproses...";
    div.appendChild(dot);
    div.appendChild(span);
    var track = document.createElement("div");
    track.className = "progress-track typing-progress";
    var fill = document.createElement("div");
    fill.className = "progress-fill";
    fill.id = "typing-progress-fill";
    fill.style.width = "0%";
    track.appendChild(fill);
    div.appendChild(track);
    var count = document.createElement("span");
    count.className = "typing-count";
    count.id = "typing-progress-count";
    count.textContent = "Menyiapkan pekerjaan...";
    div.appendChild(count);
    var cancel = document.createElement("button");
    cancel.className = "button button--secondary typing-cancel";
    cancel.type = "button";
    cancel.textContent = "Batalkan task";
    cancel.addEventListener("click", async function () {
      if (!state.currentTaskId) return;
      cancel.disabled = true;
      try {
        var result = await BERESIN.api("POST", "/user/tasks/" + state.currentTaskId + "/cancel");
        setTypingText(result.status === "CANCELLING" ? "Sedang membatalkan dengan aman..." : "Task dibatalkan", null);
      } catch (err) { cancel.disabled = false; BERESIN.showError(err.message); }
    });
    div.appendChild(cancel);
    els.chatMessages.appendChild(div);
    scrollToBottom();
  }

  function setTypingText(text, percent, processed, total) {
    var t = BERESIN.el("typing-indicator");
    if (t) {
      var span = t.querySelector(".typing-text");
      if (span) span.textContent = text;
      var fill = BERESIN.el("typing-progress-fill");
      if (fill && typeof percent === "number") fill.style.width = Math.max(0, Math.min(100, percent)) + "%";
      var count = BERESIN.el("typing-progress-count");
      if (count && total > 0) count.textContent = processed + " / " + total + " file diproses";
    }
  }

  function removeTyping() {
    var t = BERESIN.el("typing-indicator");
    if (t) t.remove();
    state.currentTaskId = null;
  }

  function scrollToBottom() {
    var area = qs(".workspace");
    if (area) area.scrollTop = area.scrollHeight;
  }

  async function sendMessage(text, composerInput) {
    var onlineDevices = state.devices.filter(function (device) { return device.status === "ONLINE"; });
    if (onlineDevices.length > 1 && !state.selectedDeviceId) {
      throw new Error("Pilih perangkat tujuan terlebih dahulu.");
    }
    if (!state.activeId) {
      // First message creates a conversation implicitly.
      var created = await BERESIN.api("POST", "/user/conversations", { title: text.slice(0, 60) });
      state.activeId = created.conversation_id;
      state.conversations.unshift({ id: created.conversation_id, title: created.title || text.slice(0, 60), updated_at: new Date().toISOString() });
      renderHistory();
    }
    showChatArea();
    if (composerInput) composerInput.value = "";
    appendMessage("user", text);
    scrollToBottom();
    appendTyping();
    try {
      // The server queues the task and returns immediately (async worker).
      var resp = await BERESIN.api("POST", "/user/conversations/" + state.activeId + "/messages", {
        content: text,
        device_id: state.selectedDeviceId,
      });
      if (resp.status === "PROCESSING") {
        state.currentTaskId = resp.task_id;
        consumeTaskStream(resp.task_id);
        await pollTask(resp.task_id);
      } else if (resp.status === "COMPLETED" || resp.status === "WAITING_APPROVAL") {
        removeTyping();
        if (resp.reply) {
          appendMessage("assistant", resp.reply);
          scrollToBottom();
        }
        if (resp.status === "WAITING_APPROVAL" && resp.approvals && resp.approvals.length) {
          renderApprovalNotice(resp.approvals[0]);
        }
      }
      // Refresh conversation list to reflect updated titles/times.
      loadConversations();
    } catch (err) {
      removeTyping();
      appendMessage("assistant", "Maaf, saya belum dapat menyelesaikan permintaan tersebut. " + err.message);
      scrollToBottom();
    }
  }

  async function consumeTaskStream(taskId) {
    try {
      var resp = await fetch("/api/user/tasks/" + taskId + "/events", {
        headers: { Authorization: "Bearer " + BERESIN.getToken() },
      });
      if (!resp.ok || !resp.body) return;
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      while (true) {
        var part = await reader.read();
        if (part.done) break;
        buffer += decoder.decode(part.value, { stream: true });
        var frames = buffer.split("\n\n");
        buffer = frames.pop();
        frames.forEach(function (frame) {
          var line = frame.split("\n").find(function (x) { return x.indexOf("data: ") === 0; });
          if (!line) return;
          try {
            var ev = JSON.parse(line.slice(6));
            if (ev.type === "progress") {
              var label = ev.status === "VERIFYING" ? "Memverifikasi hasil" : "BERESIN sedang mengerjakan";
              setTypingText(label + "... " + Math.round(ev.progress || 0) + "%", ev.progress, ev.processed_count, ev.total_count);
            } else if (ev.type === "assistant_delta") {
              setTypingText("BERESIN sedang menulis jawaban...", null);
              if (!state.streamingDraft) {
                state.streamingDraft = appendMessage("assistant", "");
                state.streamingDraft.classList.add("message--streaming");
              }
              state.streamingDraft.querySelector("p").textContent += ev.delta || "";
              scrollToBottom();
            }
          } catch (e) { /* malformed event: polling remains the fallback */ }
        });
      }
    } catch (e) { /* polling remains the fallback */ }
  }

  async function pollTask(taskId) {
    var attempts = 0;
    while (attempts < 120) {
      await new Promise(function (r) { setTimeout(r, 1500); });
      attempts += 1;
      var task;
      try {
        task = await BERESIN.api("GET", "/user/tasks/" + taskId);
      } catch (err) {
        removeTyping();
        appendMessage("assistant", "Tidak dapat memeriksa status tugas: " + err.message);
        return;
      }
      var status = task.status;
      if (status === "VERIFYING") {
        setTypingText("Memverifikasi hasil... " + Math.round(task.progress || 0) + "%", task.progress, task.processed_count, task.total_count);
      } else if (status === "RUNNING" || status === "PLANNING") {
        setTypingText("BERESIN sedang mengerjakan... " + Math.round(task.progress || 0) + "%", task.progress, task.processed_count, task.total_count);
      } else if (status === "COMPLETED" || status === "FAILED" || status === "CANCELLED" || status === "WAITING_APPROVAL") {
        removeTyping();
        if (status === "COMPLETED") {
          // Load final assistant message(s) from the conversation.
          try {
            var msgs = await BERESIN.api("GET", "/user/conversations/" + state.activeId + "/messages");
            var lastAssistant = null;
            msgs.forEach(function (m) { if (m.role === "assistant") lastAssistant = m.content; });
            if (state.streamingDraft) {
              state.streamingDraft.remove();
              state.streamingDraft = null;
            }
            appendMessage("assistant", lastAssistant || "Selesai.");
            // Structured recommendations produced by folder_organizer.
            var rawResult = task.result_json || null;
            if (rawResult) {
              try {
                var parsed = typeof rawResult === "string" ? JSON.parse(rawResult) : rawResult;
                var events = parsed.tool_events || [];
                events.forEach(function (ev) {
                  if (ev.tool === "folder_organizer" && ev.result && ev.result.recommendations && ev.result.recommendations.length) {
                    renderRecommendations(taskId, ev.result.directory, ev.result.recommendations);
                  }
                });
              } catch (e) { /* ignore */ }
            }
          } catch (e) {
            appendMessage("assistant", "Selesai.");
          }
        } else if (status === "FAILED") {
          appendMessage("assistant", "Maaf, tugas tidak dapat diselesaikan. " + (task.error || "Silakan coba lagi."));
        } else if (status === "WAITING_APPROVAL") {
          // Pending approvals are surfaced in the conversation UI.
          try {
            var approvals = await BERESIN.api("GET", "/user/approvals");
            if (approvals.length) renderApprovalNotice(approvals[approvals.length - 1]);
            appendMessage("assistant", "Tindakan berikut memerlukan persetujuan Anda sebelum dilanjutkan.");
          } catch (e) { /* ignore */ }
        }
        scrollToBottom();
        return;
      }
      // Still processing: keep the typing indicator alive with progress.
    }
    removeTyping();
    appendMessage("assistant", "Permintaan masih diproses. Periksa kembali sebentar lagi.");
  }

  function renderRecommendations(sourceTaskId, directory, recommendations) {
    var intro = document.createElement("div");
    intro.className = "recommendations-intro";
    var p = document.createElement("p");
    p.textContent = "Saya menemukan beberapa rekomendasi berikut. Pilih yang ingin diterapkan:";
    intro.appendChild(p);
    els.chatMessages.appendChild(intro);

    recommendations.forEach(function (rec, index) {
      var card = document.createElement("div");
      card.className = "recommendation-card";
      card.id = "rec-" + rec.id;

      var title = document.createElement("h3");
      title.textContent = (index + 1) + ". " + rec.title;
      var desc = document.createElement("p");
      desc.className = "recommendation-desc";
      desc.textContent = rec.description;
      var count = document.createElement("div");
      count.className = "recommendation-count";
      count.textContent = rec.file_count + " file";

      // detail summary (folder counts / groups)
      var detailEl = document.createElement("div");
      detailEl.className = "recommendation-detail";
      if (rec.detail && typeof rec.detail === "object") {
        var keys = Object.keys(rec.detail).slice(0, 6);
        keys.forEach(function (k) {
          var chip = document.createElement("span");
          chip.className = "recommendation-chip";
          chip.textContent = k + ": " + rec.detail[k];
          detailEl.appendChild(chip);
        });
      }

      var actions = document.createElement("div");
      actions.className = "button-row";
      var applyBtn = document.createElement("button");
      applyBtn.className = "button button--primary";
      applyBtn.textContent = "Terapkan " + (index + 1);
      applyBtn.addEventListener("click", function () { applyRecommendation(sourceTaskId, rec, card); });
      actions.appendChild(applyBtn);

      card.appendChild(title);
      card.appendChild(desc);
      card.appendChild(count);
      if (detailEl.childNodes.length) card.appendChild(detailEl);
      card.appendChild(actions);
      els.chatMessages.appendChild(card);
    });
    scrollToBottom();
  }

  async function applyRecommendation(sourceTaskId, rec, card) {
    try {
      var resp = await BERESIN.api("POST", "/user/recommendations/apply", {
        source_task_id: sourceTaskId,
        recommendation_id: rec.id,
      });
      if (card) card.remove();
      appendMessage("assistant", "Rekomendasi memerlukan persetujuan Anda sebelum dijalankan.");
      // Approval card appears once pending approvals load.
      var approvals = await BERESIN.api("GET", "/user/approvals");
      var pending = approvals.filter(function (a) { return String(a.id) === String(resp.approval_id); });
      if (pending.length) renderApprovalNotice(pending[0]);
      scrollToBottom();
    } catch (err) {
      BERESIN.showError(err.message);
    }
  }

  function renderApprovalNotice(approval) {
    var section = document.createElement("section");
    section.className = "approval-summary";
    var approvalId = approval.approval_id || approval.id;
    section.id = "approval-" + approvalId;
    var kicker = document.createElement("p");
    kicker.className = "approval-kicker";
    kicker.textContent = "Memerlukan persetujuan Anda";
    var title = document.createElement("h2");
    title.textContent = approval.action || approval.tool_name || approval.tool || "Tindakan pada file";
    var note = document.createElement("p");
    note.textContent = approval.risk || "Tinjau tindakan ini sebelum BERESIN melanjutkan.";
    var detail = document.createElement("div");
    detail.className = "approval-review";
    detail.hidden = true;
    detail.textContent = "Cakupan: " + (approval.scope || "Tidak tersedia") + ". Risiko: " + (approval.risk || "Perubahan file") + ".";
    var actions = document.createElement("div");
    actions.className = "approval-actions";
    var approve = document.createElement("button");
    approve.className = "button button--primary";
    approve.textContent = "Setujui";
    approve.addEventListener("click", function () { respondApproval(approvalId, "APPROVED", section); });
    var review = document.createElement("button");
    review.className = "button button--secondary";
    review.textContent = "Tinjau";
    review.addEventListener("click", function () { detail.hidden = !detail.hidden; });
    var reject = document.createElement("button");
    reject.className = "button button--danger";
    reject.textContent = "Batalkan";
    reject.addEventListener("click", function () { respondApproval(approvalId, "REJECTED", section); });
    actions.appendChild(review);
    actions.appendChild(approve);
    actions.appendChild(reject);
    section.appendChild(kicker);
    section.appendChild(title);
    section.appendChild(note);
    section.appendChild(detail);
    section.appendChild(actions);
    els.chatMessages.appendChild(section);
    scrollToBottom();
  }

  async function respondApproval(id, decision, section) {
    try {
      var resp = await BERESIN.api("POST", "/user/approvals/" + id + "/respond", { decision: decision });
      if (section) section.remove();
      if (decision === "APPROVED") {
        BERESIN.showToast("Persetujuan diberikan. Tindakan sedang dijalankan.", "success");
        appendMessage("assistant", "Terima kasih. Tindakan Anda sudah disetujui dan sedang dijalankan.");
      } else {
        BERESIN.showToast("Tindakan ditolak.", "success");
        appendMessage("assistant", "Baik, tindakan tersebut dibatalkan.");
      }
      scrollToBottom();
      // The approve endpoint executes synchronously, so refresh task state.
      if (resp && resp.task_id) {
        try {
          var task = await BERESIN.api("GET", "/user/tasks/" + resp.task_id);
          if (task.status === "COMPLETED") {
            appendMessage("assistant", "Tindakan selesai dijalankan dan diverifikasi.");
            scrollToBottom();
          } else if (task.status === "FAILED") {
            appendMessage("assistant", "Tindakan gagal dijalankan: " + (task.error || ""));
            scrollToBottom();
          }
        } catch (e) { /* ignore */ }
      }
    } catch (err) {
      BERESIN.showError(err.message);
    }
  }

  async function onSubmitEmpty(e) {
    e.preventDefault();
    var text = els.message.value.trim();
    if (!text || state.sending) return;
    state.sending = true;
    try {
      await sendMessage(text, els.message);
    } finally {
      state.sending = false;
    }
  }

  async function onSubmitActive(e) {
    e.preventDefault();
    var text = els.activeMessage.value.trim();
    if (!text || state.sending) return;
    state.sending = true;
    try {
      await sendMessage(text, els.activeMessage);
    } finally {
      state.sending = false;
      els.activeMessage.focus();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
