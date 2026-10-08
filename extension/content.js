if (window.top === window) {
  const HOST_ID = "resume-tailor-host";

  function googleJobsOpen() {
    if (!/(^|\.)google\./i.test(location.hostname)) return true;
    const params = new URLSearchParams(location.search);
    const ibp = params.get("ibp") || "";
    if (ibp.includes("jobs") || params.get("udm") === "8") return true;
    return !!document.querySelector(".whazf, .HBvzbc, .YgLbBe, .iFjolb, [class*='jobDescription']");
  }

  function skim(call) {
    if (call === "Yes") return "10-second skim: interview.";
    if (call === "No") return "10-second skim: likely no.";
    return "10-second skim: not sure yet.";
  }

  function ensureHost() {
    let host = document.getElementById(HOST_ID);
    if (host) return host;
    host = document.createElement("div");
    host.id = HOST_ID;
    host.style.all = "initial";
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        :host { all: initial; }
        .dock {
          position: fixed;
          right: 16px;
          bottom: 16px;
          z-index: 2147483647;
          font: 13px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          color: #1c1917;
        }
        button {
          font: inherit;
          cursor: pointer;
        }
        .go {
          border: 0;
          border-radius: 999px;
          padding: 10px 16px;
          background: #1c1917;
          color: #fff;
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
        }
        .go:disabled { opacity: 0.6; cursor: default; }
        .panel {
          width: 300px;
          margin-bottom: 8px;
          padding: 12px;
          border-radius: 12px;
          background: #fff;
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.2);
        }
        .panel h2 { margin: 0 0 8px; font-size: 14px; }
        .muted { color: #57534e; }
        .model {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
          color: #1c1917;
        }
        .model span { font-size: 12px; color: #57534e; }
        .model select {
          flex: 1;
          font: inherit;
          border: 1px solid #e7e5e4;
          border-radius: 8px;
          padding: 6px 8px;
          background: #fff;
          color: #1c1917;
        }
        .row { display: flex; gap: 8px; margin-top: 10px; }
        .row button, .close {
          border: 0;
          border-radius: 8px;
          padding: 8px 10px;
          background: #1c1917;
          color: #fff;
        }
        .close { background: #e7e5e4; color: #1c1917; }
        ul { margin: 8px 0 0; padding-left: 18px; }
      </style>
      <div class="dock">
        <div class="panel" hidden>
          <h2>Resume Tailor</h2>
          <div class="body"></div>
          <div class="row">
            <button type="button" class="pdf" hidden>Download PDF</button>
            <button type="button" class="cover" hidden>Cover letter</button>
            <button type="button" class="close">Close</button>
          </div>
        </div>
        <label class="model"><span>Model</span><select class="models"></select></label>
        <button type="button" class="go">Tailor</button>
      </div>
    `;
    document.documentElement.appendChild(host);
    const panel = shadow.querySelector(".panel");
    const body = shadow.querySelector(".body");
    const go = shadow.querySelector(".go");
    const models = shadow.querySelector(".models");
    const pdf = shadow.querySelector(".pdf");
    const cover = shadow.querySelector(".cover");
    shadow.querySelector(".close").addEventListener("click", () => {
      panel.hidden = true;
    });
    let port = null;
    let resumeId = null;

    function show(text) {
      panel.hidden = false;
      body.replaceChildren();
      const paragraph = document.createElement("p");
      paragraph.textContent = text;
      body.appendChild(paragraph);
    }

    function showResult(result) {
      panel.hidden = false;
      body.replaceChildren();
      const audit = result.audit || {};
      const lines = [
        skim(audit.interview),
        audit.ats_score == null ? "" : `Match ${audit.ats_score}% / target ${audit.ats_target || 97}`,
        ...(audit.reject_reasons || []).slice(0, 3),
      ].filter(Boolean);
      for (const line of lines) {
        const paragraph = document.createElement("p");
        paragraph.textContent = line;
        body.appendChild(paragraph);
      }
      const gaps = audit.gaps || [];
      if (!gaps.length) {
        const none = document.createElement("p");
        none.className = "muted";
        none.textContent = "No unsupported requirements.";
        body.appendChild(none);
      } else {
        const list = document.createElement("ul");
        for (const gap of gaps.slice(0, 6)) {
          const item = document.createElement("li");
          item.textContent = gap;
          list.appendChild(item);
        }
        body.appendChild(list);
      }
      downloads(result.resume_id);
    }

    function downloads(id) {
      resumeId = id || null;
      pdf.hidden = !resumeId;
      cover.hidden = !resumeId;
    }

    async function save(kind) {
      if (!resumeId) return;
      const response = await chrome.runtime.sendMessage({ type: "download", resumeId, kind });
      if (!response || !response.ok) {
        show((response && response.detail) || "Could not download the file.");
      }
    }

    function choiceLabel(choice) {
      if (choice.id === "auto") return "Auto";
      if (choice.id === "select") return "Original bullets";
      const left = typeof choice.remaining_tailors === "number" ? ` · ${choice.remaining_tailors} left` : "";
      return `${choice.label || choice.id}${left}`;
    }

    function fillModels(state) {
      const choices = (state && state.choices) || [{ id: "auto", label: "Auto" }];
      const provider = (state && state.provider) || "auto";
      models.replaceChildren();
      for (const choice of choices) {
        const option = document.createElement("option");
        option.value = choice.id;
        option.textContent = choiceLabel(choice);
        const blocked =
          choice.configured === false ||
          (choice.id !== "auto" &&
            choice.id !== "select" &&
            typeof choice.remaining_tailors === "number" &&
            choice.remaining_tailors <= 0);
        option.disabled = blocked;
        models.appendChild(option);
      }
      models.value = [...models.options].some((option) => option.value === provider) ? provider : "auto";
    }

    models.addEventListener("change", () => {
      chrome.runtime.sendMessage({ type: "set-model", provider: models.value });
    });
    chrome.runtime.sendMessage({ type: "models" }, (response) => {
      if (response && response.ok) fillModels(response.result);
      else fillModels({ provider: "auto", choices: [{ id: "auto", label: "Auto", configured: true }] });
    });

    pdf.addEventListener("click", () => save("resume"));
    cover.addEventListener("click", () => save("cover"));

    go.addEventListener("click", () => {
      if (go.disabled) return;
      const job = extractJob();
      go.disabled = true;
      downloads(null);
      show("Reading this posting…");
      const previous = port;
      const connection = chrome.runtime.connect({ name: "tailor" });
      port = connection;
      if (previous) previous.disconnect();
      connection.onMessage.addListener((message) => {
        if (message.type === "progress") {
          const event = message.event || {};
          const score = event.score == null ? "" : ` Match ${event.score}%.`;
          show(`${event.message || "Working…"}${score}`);
          return;
        }
        go.disabled = false;
        if (message.type === "error") {
          show(message.detail || "Tailor failed.");
          return;
        }
        if (message.type === "result") showResult(message.event || {});
      });
      connection.onDisconnect.addListener(() => {
        if (port === connection) go.disabled = false;
      });
      connection.postMessage({ type: "start", job });
    });

    return host;
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (!message || message.type !== "tailor-now") return;
    const host = ensureHost();
    const button = host.shadowRoot && host.shadowRoot.querySelector(".go");
    if (button) button.click();
  });

  function sync() {
    if (!googleJobsOpen()) {
      const existing = document.getElementById(HOST_ID);
      if (existing) existing.remove();
      return;
    }
    ensureHost();
  }

  sync();
  let timer = 0;
  const observer = new MutationObserver(() => {
    window.clearTimeout(timer);
    timer = window.setTimeout(sync, 400);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
}
