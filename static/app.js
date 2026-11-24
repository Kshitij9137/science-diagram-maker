const CHECK_LABELS = {
  valid_xml: "Valid XML",
  viewbox_bounds: "Inside viewBox",
  title_and_labels: "Title + labels",
  animation: "Animation",
  security: "Security",
};

// Small helper: make an element with a class and some text
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// SVG shown through <img> can't run scripts. It needs the xmlns attribute to render.
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

function renderRow(result) {
  const row = el("tr");

  // 1. Concept
  const conceptCell = el("td");
  conceptCell.append(
    el("strong", "", result.concept_name),
    el("div", "muted", result.subject),
    el("span", "badge " + (result.status === "passed" ? "pass" : "fail"),
       result.status === "passed" ? "All checks passed" : "Some checks failed"),
    el("div", "muted small", "Model: " + result.model)
  );

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

  row.append(conceptCell, diagramCell, checksCell, costCell, retriesCell);
  return row;
}

async function loadResults() {
  try {
    const response = await fetch("/api/results");
    if (!response.ok) throw new Error("Server returned " + response.status);
    const data = await response.json();
    if (!data.results.length) {
      showError("No saved results found. Run: python -m scripts.generate_all");
      return;
    }
    const body = document.getElementById("results-body");
    data.results.forEach((result) => body.append(renderRow(result)));
    document.getElementById("results-table").hidden = false;
  } catch (error) {
    showError("Could not load results: " + error.message);
  } finally {
    document.getElementById("loading").hidden = true;
  }
}

loadResults();