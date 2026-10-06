const $ = (id) => document.getElementById(id);

function showSession(state) {
  const signedIn = !!(state && state.signedIn);
  $("login").hidden = signedIn;
  $("session").hidden = !signedIn;
  if (!signedIn) return;
  $("who").textContent = state.email || "Signed in";
  $("resume").textContent = state.uploaded
    ? "Resume on file. Open a job and click Tailor on the page."
    : "No resume yet. Upload one in the app, then come back.";
}

function fillModels(select, state) {
  const choices = (state && state.choices) || [];
  const provider = (state && state.provider) || "auto";
  select.replaceChildren();
  for (const choice of choices) {
    const option = document.createElement("option");
    option.value = choice.id;
    option.textContent = choiceLabel(choice);
    option.disabled = !choiceEnabled(choice);
    select.appendChild(option);
  }
  if (![...select.options].some((option) => option.value === provider)) {
    const option = document.createElement("option");
    option.value = "auto";
    option.textContent = "Auto";
    select.appendChild(option);
  }
  select.value = [...select.options].some((option) => option.value === provider) ? provider : "auto";
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

async function loadModels() {
  const select = $("model");
  if (!select) return;
  const response = await chrome.runtime.sendMessage({ type: "models" });
  if (!response || !response.ok) return;
  fillModels(select, response.result);
}

async function refresh() {
  const response = await chrome.runtime.sendMessage({ type: "session" });
  if (!response || !response.ok) {
    $("status").textContent = (response && response.detail) || "API not reachable. Start: python -m backend.main";
    showSession({ signedIn: false });
    return;
  }
  $("status").textContent = "";
  showSession(response.result);
  if (response.result && response.result.signedIn) loadModels();
}

$("login").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("status").textContent = "Signing in…";
  const response = await chrome.runtime.sendMessage({
    type: "login",
    email: $("email").value.trim(),
    password: $("password").value,
  });
  if (!response || !response.ok) {
    $("status").textContent = (response && response.detail) || "Could not sign in.";
    return;
  }
  $("password").value = "";
  $("status").textContent = "";
  showSession(response.result);
  loadModels();
});

$("model").addEventListener("change", async () => {
  await chrome.runtime.sendMessage({ type: "set-model", provider: $("model").value });
});

$("signout").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "logout" });
  showSession({ signedIn: false });
  $("status").textContent = "";
});

$("this-tab").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) return;
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "tailor-now" });
    $("status").textContent = "Tailor is running on this page.";
    return;
  } catch {
    /* this site has no on-page button */
  }
  $("status").textContent = "Reading this tab…";
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["extract.js"] });
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => globalThis.__resumeTailorExtract(),
    });
    const port = chrome.runtime.connect({ name: "tailor" });
    port.onMessage.addListener((message) => {
      if (message.type === "progress") {
        const event = message.event || {};
        $("status").textContent = event.message || "Working…";
      } else if (message.type === "error") {
        $("status").textContent = message.detail || "Tailor failed.";
      } else if (message.type === "result") {
        const event = message.event || {};
        const audit = event.audit || {};
        const call = audit.interview === "Yes" ? "interview" : audit.interview === "No" ? "likely no" : "not sure yet";
        $("status").textContent = `Done. 10-second skim: ${call}. Match ${audit.ats_score}%.`;
        if (event.resume_id) {
          chrome.runtime.sendMessage({ type: "download", resumeId: event.resume_id, kind: "resume" });
        }
      }
    });
    port.postMessage({ type: "start", job: result });
  } catch (err) {
    $("status").textContent = "Could not read this tab. Open the job page and try again.";
  }
});

refresh();
