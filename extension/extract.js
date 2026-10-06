function hostIs(host, suffix) {
  return host === suffix || host.endsWith("." + suffix);
}

function extractJob() {
  const host = location.hostname.toLowerCase();
  const google = /(^|\.)google\./i.test(host);
  const adapters = [
    {
      match: (name) => hostIs(name, "linkedin.com"),
      selectors: [
        ".jobs-description__content",
        ".jobs-box__html-content",
        ".jobs-description",
        "#job-details",
      ],
      role: [
        ".job-details-jobs-unified-top-card__job-title",
        "h1.t-24",
        ".jobs-unified-top-card__job-title",
        "h1",
      ],
      company: [
        ".job-details-jobs-unified-top-card__company-name",
        ".jobs-unified-top-card__company-name",
        "a.topcard__org-name-link",
      ],
    },
    {
      match: (name) => hostIs(name, "naukri.com"),
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
      match: (name) => /(^|\.)indeed\./i.test(name),
      selectors: [
        "#jobDescriptionText",
        ".jobsearch-JobComponent-description",
        "#jobDescription",
      ],
      role: [
        "h1.jobsearch-JobInfoHeader-title",
        "[data-testid='jobsearch-JobInfoHeader-title']",
        "h1",
      ],
      company: [
        "[data-testid='inlineHeader-companyName']",
        "[data-company-name='true']",
        ".jobsearch-InlineCompanyRating",
      ],
    },
    {
      match: (name) => /(^|\.)glassdoor\./i.test(name),
      selectors: [
        "[data-test='jobDescription']",
        "[data-test='description']",
        ".JobDetails_jobDescription__uW_fK",
        "#JobDescriptionContainer",
      ],
      role: ["[data-test='job-title']", "h1"],
      company: ["[data-test='employer-name']", "[data-test='employerName']"],
    },
    {
      match: (name) => hostIs(name, "foundit.in") || hostIs(name, "monster.com") || hostIs(name, "monsterindia.com"),
      selectors: [".jobDesc", "#jobDescription", ".job-description", "[class*='jobdesc']"],
      role: ["h1", ".jobTitle"],
      company: [".company-name", ".companyName"],
    },
    {
      match: (name) => hostIs(name, "cutshort.io"),
      selectors: ["#job-description-section", ".job-description", "[class*='JobDescription']"],
      role: ["h1"],
      company: ["[class*='company-name']", "h2"],
    },
    {
      match: (name) =>
        hostIs(name, "greenhouse.io") ||
        hostIs(name, "lever.co") ||
        hostIs(name, "myworkdayjobs.com") ||
        hostIs(name, "ashbyhq.com"),
      selectors: [
        "[data-automation-id='jobPostingDescription']",
        "#content",
        ".job-post",
        "[data-qa='job-description']",
        ".posting-page",
        ".section-wrapper",
        "[class*='job-description']",
      ],
      role: ["h1", ".posting-headline h2", "[data-automation-id='jobPostingHeader']"],
      company: [".company-name", "h2"],
    },
    {
      match: () => google,
      selectors: [".whazf", ".HBvzbc", ".YgLbBe", "[class*='jobDescription']"],
      role: ["h2.iFjolb", ".KLsYvd", "h2"],
      company: [".a3jPc", ".nJlQNd", ".vNEEBe"],
    },
  ];

  function firstText(selectors) {
    for (const selector of selectors || []) {
      const el = document.querySelector(selector);
      if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
    }
    return "";
  }

  function fromElement(el, extractor, adapter) {
    return {
      extractor,
      role: firstText(adapter && adapter.role) || document.title,
      company: firstText(adapter && adapter.company),
      text: el.innerText.trim(),
      url: location.href,
    };
  }

  const jsonNodes = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .map((el) => {
      try {
        return JSON.parse(el.textContent || "");
      } catch {
        return null;
      }
    })
    .flatMap((node) => (Array.isArray(node) ? node : node && node["@graph"] ? node["@graph"] : [node]));

  const jsonld = jsonNodes.find(
    (node) => node && (node["@type"] === "JobPosting" || node.type === "JobPosting")
  );
  if (jsonld && (jsonld.description || jsonld.title)) {
    const div = document.createElement("div");
    div.innerHTML = jsonld.description || "";
    const text = (div.innerText || jsonld.description || "").trim();
    if (text.length > 80) {
      return {
        extractor: "jsonld",
        role: jsonld.title || document.title,
        company: (jsonld.hiringOrganization && jsonld.hiringOrganization.name) || "",
        text,
        url: location.href,
      };
    }
  }

  const adapter = adapters.find((item) => item.match(host));
  const hostSelectors = adapter ? adapter.selectors : [];
  const generic = google
    ? []
    : ["[class*='job-description']", "[id*='job-description']", "[class*='jobDesc']", "article"];
  for (const selector of [...hostSelectors, ...generic]) {
    const el = document.querySelector(selector);
    if (el && el.innerText && el.innerText.trim().length > 80) {
      return fromElement(el, "adapter", adapter);
    }
  }

  const selected = window.getSelection && String(window.getSelection());
  if (!google && selected && selected.trim().length > 80) {
    return {
      extractor: "selection",
      role: document.title,
      company: "",
      text: selected.trim(),
      url: location.href,
    };
  }

  if (google) {
    return { extractor: "adapter", role: "", company: "", text: "", url: location.href };
  }

  const blocks = [...document.querySelectorAll("p, li")]
    .map((el) => el.innerText.trim())
    .filter((t) => t.length > 40);
  return {
    extractor: "paste",
    role: document.title,
    company: "",
    text: blocks.slice(0, 40).join("\n"),
    url: location.href,
  };
}

globalThis.__resumeTailorExtract = extractJob;
