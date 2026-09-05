function extractJob() {
  const host = location.hostname;
  const adapters = [
    {
      match: /linkedin\.com$/i,
      selectors: [
        ".jobs-description__content",
        ".jobs-box__html-content",
        ".jobs-description",
        "#job-details",
      ],
      role: [
        ".job-details-jobs-unified-top-card__job-title",
        "h1.t-24",
        "h1",
      ],
      company: [
        ".job-details-jobs-unified-top-card__company-name",
        ".jobs-unified-top-card__company-name",
        "a.topcard__org-name-link",
      ],
    },
    {
      match: /naukri\.com$/i,
      selectors: [
        ".styles_JDC__dang-inner-html__",
        ".dang-inner-html",
        ".styles_jhc__jd-container__",
        "section.job-desc",
        ".job-desc",
      ],
      role: [".styles_jd-header-title", "h1"],
      company: [".styles_jd-header-comp-name", ".jd-header-comp-name"],
    },
    {
      match: /cutshort\.io$/i,
      selectors: ["#job-description-section", ".job-description", "[class*='JobDescription']"],
      role: ["h1"],
      company: ["[class*='company-name']", "h2"],
    },
    {
      match: /(foundit\.in|monsterindia\.com|monster\.com)$/i,
      selectors: [".jobDesc", "#jobDescription", ".job-description", "[class*='jobdesc']"],
      role: ["h1", ".jobTitle"],
      company: [".company-name", ".companyName"],
    },
    {
      match: /(greenhouse\.io|lever\.co|myworkdayjobs\.com|ashbyhq\.com)$/i,
      selectors: [
        "#content",
        ".job-post",
        "[data-qa='job-description']",
        ".posting-page",
        "[class*='job-description']",
      ],
      role: ["h1", ".posting-headline h2"],
      company: [".company-name", "h2"],
    },
  ];

  function firstText(selectors) {
    for (const selector of selectors || []) {
      const el = document.querySelector(selector);
      if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
    }
    return "";
  }

  const jsonNodes = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map((el) => {
      try {
        return JSON.parse(el.textContent || "");
      } catch {
        return null;
      }
    })
    .flatMap((node) => (Array.isArray(node) ? node : [node]));

  const jsonld = jsonNodes.find(
    (node) => node && (node["@type"] === "JobPosting" || node.type === "JobPosting")
  );
  if (jsonld && (jsonld.description || jsonld.title)) {
    const div = document.createElement("div");
    div.innerHTML = jsonld.description || "";
    return {
      extractor: "jsonld",
      role: jsonld.title || document.title,
      company: (jsonld.hiringOrganization && jsonld.hiringOrganization.name) || "",
      text: (div.innerText || jsonld.description || "").trim(),
    };
  }

  const adapter = adapters.find((item) => item.match.test(host));
  const hostSelectors = adapter ? adapter.selectors : [];
  const generic = [
    "[class*='job-description']",
    "[id*='job-description']",
    "[class*='jobDesc']",
    "article",
  ];
  for (const selector of [...hostSelectors, ...generic]) {
    const el = document.querySelector(selector);
    if (el && el.innerText && el.innerText.trim().length > 80) {
      return {
        extractor: "adapter",
        role: firstText(adapter && adapter.role) || document.title,
        company: firstText(adapter && adapter.company),
        text: el.innerText.trim(),
      };
    }
  }

  const selected = window.getSelection && String(window.getSelection());
  if (selected && selected.trim().length > 80) {
    return {
      extractor: "selection",
      role: document.title,
      company: "",
      text: selected.trim(),
    };
  }

  const blocks = [...document.querySelectorAll("p, li")]
    .map((el) => el.innerText.trim())
    .filter((t) => t.length > 40);
  return {
    extractor: "paste",
    role: document.title,
    company: "",
    text: blocks.slice(0, 40).join("\n"),
  };
}

const $ = (id) => document.getElementById(id);

async function readPage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: extractJob,
  });
  window.__jobUrl = tab && tab.url;
  window.__extractor = result && result.extractor;
  if (result && result.text) {
    $("jd").value = result.text;
    if (result.role && !$("role").value) $("role").value = result.role;
    if (result.company && !$("company").value) $("company").value = result.company;
    $("status").textContent = `Captured via ${result.extractor} (${result.text.length} chars)`;
  } else {
    $("status").textContent = "Could not read a JD. Paste it manually.";
  }
}

async function tailor() {
  const job_description = $("jd").value.trim();
  if (job_description.length < 40) {
    $("status").textContent = "Need a job description (paste or Read page).";
    return;
  }
  $("status").textContent = "Running local tailor…";
  try {
    const res = await fetch("http://127.0.0.1:8000/v1/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_description,
        target_role: $("role").value,
        company: $("company").value,
        url: window.__jobUrl || "",
        extractor: window.__extractor || "paste",
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("status").textContent = data.detail || JSON.stringify(data);
      return;
    }
    $("status").textContent =
      `PDF: ${data.pdf_path}\nCover: ${data.cover_letter_path || "none"}\nInterview: ${data.audit.interview}\nGaps: ${(data.audit.gaps || []).join(", ") || "none"}`;
  } catch (err) {
    $("status").textContent = "API not reachable. Start: python -m backend.main";
  }
}

$("read").addEventListener("click", readPage);
$("tailor").addEventListener("click", tailor);
readPage();
