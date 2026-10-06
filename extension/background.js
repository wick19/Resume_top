const API = "http://127.0.0.1:8000";
const EXTRACTORS = new Set(["adapter", "jsonld", "selection", "paste", "jobs_api"]);

async function storedToken() {
  const { token } = await chrome.storage.local.get("token");
  return token || "";
}

async function storedProvider() {
  const { llm_provider: provider } = await chrome.storage.local.get("llm_provider");
  return (provider || "auto").trim().lower() || "auto";
}

function choiceLabel(choice) {
  if (choice.id === "auto") return "Auto";
  if (choice.id === "select") return "Original bullets";
  const left = typeof choice.remaining_tailors === "number" ? ` · ${choice.remaining_tailors} left` : "";
  return `${choice.label || choice.id}${left}`;
}

function choiceEnabled(choice) {
  if (choice.configured === false) return false;
  if (choice.id === "auto" || choice.id === "select") return true;
  return !(typeof choice.remaining_tailors === "number" && choice.remaining_tailors <= 0);
}

async function modelState() {
  const provider = await storedProvider();
  let choices = null;
  try {
    const res = await fetch(`${API}/health`);
    if (res.ok) {
      const body = await res.json();
      const rows = body.llm && body.llm.choices;
      if (Array.isArray(rows) && rows.length) choices = rows;
    }
  } catch {
    /* keep the saved model if the API is down */
  }
  if (!choices) {
    return { provider, choices: [{ id: "auto", label: "Auto", configured: true }] };
  }
  const usable = choices.find((row) => row.id === provider && choiceEnabled(row));
  const next = usable ? provider : "auto";
  if (next !== provider) await chrome.storage.local.set({ llm_provider: next });
  return { provider: next, choices };
}

async function authHeaders(json) {
  const token = await storedToken();
  const headers = {};
  if (json) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function readError(res) {
  const text = await res.text();
  try {
    const body = JSON.parse(text);
    return body.detail || text || res.statusText;
  } catch {
    return text || res.statusText;
  }
}

function explain(err) {
  const message = err && err.message ? err.message : "Request failed";
  if (/fetch|network|failed/i.test(message)) {
    return "API not reachable. Start: python -m backend.main";
  }
  return message;
}

async function session() {
  const token = await storedToken();
  if (!token) return { signedIn: false };
  const res = await fetch(`${API}/v1/auth/me`, { headers: await authHeaders(false) });
  if (res.status === 401) {
    await chrome.storage.local.remove(["token", "email"]);
    return { signedIn: false };
  }
  if (!res.ok) throw new Error(await readError(res));
  const me = await res.json();
  const resumeRes = await fetch(`${API}/v1/resume`, { headers: await authHeaders(false) });
  const resume = resumeRes.ok ? await resumeRes.json() : null;
  return {
    signedIn: true,
    email: me.user && me.user.email,
    uploaded: !!(resume && resume.uploaded),
  };
}

async function login(email, password) {
  const res = await fetch(`${API}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await readError(res));
  const data = await res.json();
  await chrome.storage.local.set({ token: data.token, email: data.user && data.user.email });
  return session();
}

async function logout() {
  const headers = await authHeaders(false);
  await fetch(`${API}/v1/auth/logout`, { method: "POST", headers }).catch(() => undefined);
  await chrome.storage.local.remove(["token", "email"]);
  return { signedIn: false };
}

function parseEvents(buffer) {
  const chunks = buffer.split("\n\n");
  const rest = chunks.pop() || "";
  const events = [];
  for (const chunk of chunks) {
    const line = chunk
      .split("\n")
      .map((part) => part.trim())
      .find((part) => part.startsWith("data:"));
    if (!line) continue;
    try {
      events.push(JSON.parse(line.slice(5).trim()));
    } catch {
      /* padding or a partial comment */
    }
  }
  return { events, rest };
}

async function runTailor(port, job, signal) {
  const token = await storedToken();
  if (!token) {
    port.postMessage({ type: "error", detail: "Sign in from the Resume Tailor extension first." });
    return;
  }
  const text = (job && job.text ? job.text : "").trim();
  if (text.length < 40) {
    port.postMessage({
      type: "error",
      detail: "Open the job description on this page, then click Tailor again.",
    });
    return;
  }
  let who;
  try {
    who = await session();
  } catch (err) {
    port.postMessage({ type: "error", detail: explain(err) });
    return;
  }
  if (!who.signedIn) {
    port.postMessage({ type: "error", detail: "Sign in from the Resume Tailor extension first." });
    return;
  }
  if (!who.uploaded) {
    port.postMessage({
      type: "error",
      detail: "Upload your resume in the Resume Tailor app, then click Tailor again.",
    });
    return;
  }

  const res = await fetch(`${API}/v1/tailor/stream`, {
    method: "POST",
    headers: await authHeaders(true),
    body: JSON.stringify({
      job_description: text,
      target_role: job.role || "",
      company: job.company || "",
      url: job.url || "",
      extractor: EXTRACTORS.has(job.extractor) ? job.extractor : "adapter",
      rewrite: true,
      cover_letter: true,
      llm_provider: (await modelState()).provider,
    }),
    signal,
  });
  if (!res.ok || !res.body) {
    port.postMessage({ type: "error", detail: await readError(res) });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseEvents(buffer);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      if (event.type === "progress") port.postMessage({ type: "progress", event });
      else if (event.type === "result") port.postMessage({ type: "result", event });
      else if (event.type === "error") port.postMessage({ type: "error", detail: event.detail || "Tailor failed" });
    }
  }
}

async function downloadFile(resumeId, kind) {
  const token = await storedToken();
  if (!token) throw new Error("Sign in from the Resume Tailor extension first.");
  const res = await fetch(`${API}/v1/library/${resumeId}/download?kind=${kind}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await readError(res));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const filename = kind === "cover" ? "cover-letter.txt" : "resume.pdf";
  await chrome.downloads.download({ url, filename, saveAs: true });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const run = async () => {
    if (message.type === "session") return session();
    if (message.type === "login") return login(message.email, message.password);
    if (message.type === "logout") return logout();
    if (message.type === "models") return modelState();
    if (message.type === "set-model") {
      const provider = (message.provider || "auto").trim().lower() || "auto";
      await chrome.storage.local.set({ llm_provider: provider });
      return { provider };
    }
    if (message.type === "download") {
      await downloadFile(message.resumeId, message.kind || "resume");
      return { ok: true };
    }
    return { ok: false };
  };
  run()
    .then((result) => sendResponse({ ok: true, result }))
    .catch((err) => sendResponse({ ok: false, detail: explain(err) }));
  return true;
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "tailor") return;
  const controller = new AbortController();
  let running = false;
  port.onDisconnect.addListener(() => controller.abort());
  port.onMessage.addListener((message) => {
    if (message.type !== "start" || running) return;
    running = true;
    runTailor(port, message.job, controller.signal).catch((err) => {
      if (err && err.name === "AbortError") return;
      const detail = explain(err);
      try {
        port.postMessage({ type: "error", detail });
      } catch {
        /* panel already closed */
      }
    });
  });
});
