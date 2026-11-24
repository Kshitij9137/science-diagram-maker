const CHECK_LABELS = {
  valid_xml: "Valid XML",
  viewbox_bounds: "Inside viewBox",
  title_and_labels: "Title + labels",
  animation: "Animation",
  security: "Security",
};
const REVIEWS_KEY = "sdm_reviews_v1";
const GENERATE_TIMEOUT_MS = 150000;

const rowsById = {};          // concept id -> its <tr>
let generating = false;

// ------------------------------------------------------------ small helpers
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// SVG shown through <img> cannot run scripts. It needs xmlns to render.
function svgToDataUrl(svg) {
  if (!/<svg[^>]*\sxmlns\s*=/.test(svg)) {
    svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
  }
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

function showError(message) {
  const banner = document.getElementById("error-banner");
  banner.textContent = message;
  banner.hidden = false;
}

function hideError() {
  document.getElementById("error-banner").hidden = true;
}

// ---------------------------------------------------- reviews (localStorage)
function loadReviews() {
  try {
    return JSON.parse(localStorage.getItem(REVIEWS_KEY)) || {};
  } catch (error) {
    return {};   // storage blocked or data damaged: start empty instead of crashing
  }
}

function saveReviews(reviews) {
  try {
    localStorage.setItem(REVIEWS_KEY, JSON.stringify(reviews));
  } catch (error) {
    showError("Could not save your review in this browser. Is storage blocked or full?");
  }
}

function updateReview(result, changes) {
  const reviews = loadReviews();
  const current = reviews[result.concept_id] || { status: null, note: "" };
  reviews[result.concept_id] = {
    ...current,
    ...changes,
    version: result.generated_at,          // which version of the diagram this was for
    updatedAt: new Date().toISOString(),
  };
  saveReviews(reviews);
}

function buildReviewCell(result) {
  const cell = el("td", "review-cell");
  const saved = loadReviews()[result.concept_id] || { status: null, note: "" };
  let current = saved.status;

  const statusText = el("div", "review-status");
  const approveBtn = el("button", "btn approve", "Approve");
  const rejectBtn = el("button", "btn reject", "Reject");
  const note = document.createElement("textarea");
  note.placeholder = "Reviewer note…";
  note.rows = 3;
  note.value = saved.note || "";
  note.setAttribute("aria-label", "Reviewer note for " + result.concept_name);

  const warning = el("div", "warn small",
    "This review was made for an earlier version of this diagram.");
  warning.hidden = !((saved.status || saved.note) && saved.version &&
                     saved.version !== result.generated_at);

  function paint() {
    approveBtn.classList.toggle("active", current === "approved");
    rejectBtn.classList.toggle("active", current === "rejected");
    approveBtn.setAttribute("aria-pressed", String(current === "approved"));
    rejectBtn.setAttribute("aria-pressed", String(current === "rejected"));
    statusText.textContent = current ? "Decision: " + current : "Not reviewed yet";
  }

  function choose(choice) {
    current = current === choice ? null : choice;   // clicking the active button clears it
    warning.hidden = true;
    updateReview(result, { status: current });
    paint();
  }

  approveBtn.addEventListener("click", () => choose("approved"));
  rejectBtn.addEventListener("click", () => choose("rejected"));
  note.addEventListener("input", () => {
    warning.hidden = true;
    updateReview(result, { note: note.value });
  });

  paint();
  const buttons = el("div", "btn-row");
  buttons.append(approveBtn, rejectBtn);
  cell.append(statusText, buttons, note, warning);
  return cell;
}

// ------------------------------------------------------------- table rows
function renderRow(result, isLive) {
  const row = el("tr");
  row.dataset.id = result.concept_id;

  // 1. Concept
  const conceptCell = el("td");
  conceptCell.append(
    el("strong", "", result.concept_name),
    el("div", "muted", result.subject),
    el("span", "badge " + (result.status === "passed" ? "pass" : "fail"),
       result.status === "passed" ? "All checks passed" : "Some checks failed"),
    el("div", "muted small", "Model: " + result.model)
  );
  if (isLive) {
    conceptCell.append(el("div", "badge live", "Live result (not saved on the server)"));
  }

  // 2. Diagram
  const diagramCell = el("td");
  if (result.svg) {
    const img = el("img", "diagram");
    img.src = svgToDataUrl(result.svg);
    img.alt = "Diagram: " + result.concept_name;
    diagramCell.append(img);
  } else {
    diagramCell.append(el("em", "muted", "No SVG was produced"));
  }

  // 3. Checks
  const checksCell = el("td");
  for (const [key, check] of Object.entries(result.checks)) {
    const line = el("div", "check");
    line.append(
      el("span", "badge " + (check.passed ? "pass" : "fail"),
         (check.passed ? "PASS " : "FAIL ") + (CHECK_LABELS[key] || key)),
      el("div", "muted small", check.reason)
    );
    checksCell.append(line);
  }

  // 4. Cost
  const costCell = el("td");
  costCell.append(
    el("strong", "", "$" + result.cost_usd.toFixed(6)),
    el("div", "muted small",
       `in ${result.tokens.input} / out ${result.tokens.output} / thinking ${result.tokens.thoughts} tokens`)
  );

  // 5. Retries
  const retriesCell = el("td");
  retriesCell.append(
    el("strong", "", String(result.retries.total)),
    el("div", "muted small",
       `API: ${result.retries.api}, validation: ${result.retries.validation}`)
  );

  row.append(conceptCell, diagramCell, checksCell, costCell, retriesCell,
             buildReviewCell(result));
  return row;
}

// Put a result in the table: replaces the concept's row, or adds it if new
function placeRow(result, isLive) {
  const newRow = renderRow(result, isLive);
  const old = rowsById[result.concept_id];
  if (old) {
    old.replaceWith(newRow);
  } else {
    document.getElementById("results-body").append(newRow);
  }
  rowsById[result.concept_id] = newRow;
}

// ------------------------------------------------------------ live generate
async function generate() {
  if (generating) return;   // ignore double clicks

  const select = document.getElementById("concept-select");
  const button = document.getElementById("generate-btn");
  const status = document.getElementById("generate-status");
  const conceptId = select.value;

  generating = true;
  button.disabled = true;
  select.disabled = true;
  button.classList.add("loading");
  status.textContent = "Generating… this can take up to a minute.";
  hideError();
  if (rowsById[conceptId]) rowsById[conceptId].classList.add("busy");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GENERATE_TIMEOUT_MS);

  try {
    let response;
    try {
      response = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concept_id: conceptId }),
        signal: controller.signal,
      });
    } catch (error) {
      throw new Error(
        error.name === "AbortError"
          ? "The request took too long and was cancelled. Please try again."
          : "Could not reach the server. If the site was idle it may still be waking up, so try again in a minute."
      );
    }

    let data = null;
    try { data = await response.json(); } catch (error) { /* not JSON */ }

    if (!response.ok) {
      throw new Error((data && data.error) ||
        `The server returned an error (status ${response.status}). Please try again.`);
    }
    if (!data || !data.checks) {
      throw new Error("The server sent an unreadable response.");
    }

    placeRow(data, true);
    status.textContent = data.status === "passed"
      ? `Done: ${data.concept_name} passed all checks.`
      : `Done: ${data.concept_name} failed some checks (see its row).`;
  } catch (error) {
    showError("Generation failed: " + error.message);
    status.textContent = "";
  } finally {
    clearTimeout(timer);
    generating = false;
    button.disabled = false;
    select.disabled = false;
    button.classList.remove("loading");
    if (rowsById[conceptId]) rowsById[conceptId].classList.remove("busy");
  }
}

// -------------------------------------------------------------------- start
async function init() {
  try {
    const response = await fetch("/api/results");
    if (!response.ok) throw new Error("Server returned " + response.status);
    const data = await response.json();
    if (!data.results.length) {
      showError("No saved results found. Run: python -m scripts.generate_all");
      return;
    }

    const select = document.getElementById("concept-select");
    data.results.forEach((result) => {
      placeRow(result, false);
      const option = el("option", "", `${result.concept_id}. ${result.concept_name}`);
      option.value = result.concept_id;
      select.append(option);
    });

    document.getElementById("results-table").hidden = false;
    select.disabled = false;
    const button = document.getElementById("generate-btn");
    button.disabled = false;
    button.addEventListener("click", generate);
  } catch (error) {
    showError("Could not load results: " + error.message);
  } finally {
    document.getElementById("loading").hidden = true;
  }
}

init();