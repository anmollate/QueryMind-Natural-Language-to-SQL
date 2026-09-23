/* ============================================================
   QueryMind Studio — front-end behaviour

   Talks to the FastAPI service (main.py) across its four staged
   endpoints (schema extraction -> generation -> execution ->
   judge). The UI's three buttons map directly onto these calls:

     POST {API_BASE}/generate_sql_query   { query }
       -> { generated_sql_query }                (Generate SQL)

     GET  {API_BASE}/get_results
       -> { results }                            (Run Query)

     GET  {API_BASE}/get_judgement
       -> { sql_validity_score/reason,
            schema_correctness_score/reason,
            semantic_correctness_score/reason,
            overall_correctness_score/reason,
            final_verdict }                      (Run Query, analysis)

     GET  {API_BASE}/get_reasoning
       -> { reasoning }                          (Explain Logic)

   The backend keeps the last generated query in a single global
   dict (query_results), so these calls are stateful and must be
   made in order: generate -> (results / judgement) -> reasoning.
   ============================================================ */

(function () {
  "use strict";

  // Point this at wherever uvicorn is serving the FastAPI app.
  const API_BASE = "http://localhost:8000";

  // Judge scores are assumed to be 0-1 floats. If your judge LLM
  // returns a different scale (e.g. 1-5), adjust this threshold.
  const SCORE_PASS_THRESHOLD = 0.6;

  let lastSql = null;
  let lastReasoning = null; // string, fetched lazily
  let currentPage = 1;
  const PAGE_SIZE = 4;

  /* ---------- backend calls ---------- */

  async function generateSql(question) {
    const res = await fetch(`${API_BASE}/generate_sql_query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: question }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${res.status})`);
    }
    const data = await res.json();
    return data.generated_sql_query;
  }

  async function fetchResults() {
    const res = await fetch(`${API_BASE}/get_results`);
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${res.status})`);
    }
    const data = await res.json();
    return normalizeResults(data.results);
  }

  async function fetchReasoning() {
    const res = await fetch(`${API_BASE}/get_reasoning`);
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${res.status})`);
    }
    const data = await res.json();
    return data.reasoning;
  }

  async function fetchJudgement() {
    const res = await fetch(`${API_BASE}/get_judgement`);
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${res.status})`);
    }
    const data = await res.json();
    return normalizeJudgement(data);
  }

  /* ---------- shape adapters ----------
     TextToSQLEngine / llm_as_a_Judge weren't included, so these
     guess at reasonable shapes for `results` and the judge scores.
     Adjust if the real shapes turn out different.
  */
  function normalizeResults(results) {
    if (!results) return { columns: [], rows: [] };
    // Already { columns, rows }?
    if (!Array.isArray(results) && results.columns && results.rows) {
      return { columns: results.columns, rows: results.rows };
    }
    if (!Array.isArray(results) || results.length === 0) {
      return { columns: [], rows: [] };
    }
    // Array of row objects, e.g. [{col: val, ...}, ...]
    if (typeof results[0] === "object" && !Array.isArray(results[0])) {
      const columns = Object.keys(results[0]);
      const rows = results.map((r) => columns.map((c) => r[c]));
      return { columns, rows };
    }
    // Array of arrays with no column names available.
    const columns = results[0].map((_, i) => `col_${i + 1}`);
    return { columns, rows: results };
  }

  function isPassing(score) {
    if (typeof score === "boolean") return score;
    if (typeof score === "number") return score >= SCORE_PASS_THRESHOLD;
    if (typeof score === "string") return /pass|yes|true|satisfactory/i.test(score);
    return true;
  }

  function normalizeJudgement(j) {
    const rawChecks = [
      { label: "SQL validity", score: j.sql_validity_score, detail: j.sql_validity_reason },
      { label: "Schema correctness", score: j.schema_correctness_score, detail: j.schema_correctness_reason },
      { label: "Semantic correctness", score: j.semantic_correctness_score, detail: j.semantic_correctness_reason },
      { label: "Overall correctness", score: j.overall_correctness_score, detail: j.overall_correctness_reason },
    ];
    const checks = rawChecks.map((c) => ({
      label: c.label,
      passed: isPassing(c.score),
      detail: c.detail != null ? String(c.detail) : "",
    }));

    let verdict = "satisfactory";
    if (typeof j.final_verdict === "boolean") {
      verdict = j.final_verdict ? "satisfactory" : "unsatisfactory";
    } else if (typeof j.final_verdict === "string") {
      verdict = /unsatisfactory|fail|no/i.test(j.final_verdict) ? "unsatisfactory" : "satisfactory";
    }

    return { verdict, checks };
  }

  /* ---------------------------------------------------------
     DOM wiring — only runs on studio.html
     --------------------------------------------------------- */
  const sqlOutput = document.getElementById("sql-output");
  const questionInput = document.getElementById("question-input");
  const chips = document.querySelectorAll(".chip");
  const runBtn = document.getElementById("run-btn");
  const explainBtn = document.getElementById("explain-btn");
  const explainBox = document.getElementById("explain-box");
  const resultsBody = document.getElementById("results-body");
  const copyBtn = document.getElementById("copy-btn");
  const askBtn = document.getElementById("ask-btn");
  const analysisBody = document.getElementById("analysis-body");

  if (sqlOutput) {
    // load the first suggested prompt on page open
    const firstChip = document.querySelector(".chip.active") || chips[0];
    if (firstChip) {
      questionInput.value = firstChip.textContent;
      handleAsk(firstChip.textContent);
    }

    chips.forEach((chip) => {
      chip.addEventListener("click", () => {
        chips.forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        questionInput.value = chip.textContent;
        handleAsk(chip.textContent);
      });
    });

    askBtn.addEventListener("click", () => handleAsk(questionInput.value));
    questionInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleAsk(questionInput.value);
    });

    runBtn.addEventListener("click", handleRun);
    explainBtn.addEventListener("click", handleExplain);

    copyBtn.addEventListener("click", () => {
      const text = sqlOutput.textContent;
      navigator.clipboard?.writeText(text).then(() => {
        copyBtn.innerHTML = "✓";
        setTimeout(() => {
          copyBtn.innerHTML =
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>';
        }, 1200);
      });
    });
  }

  async function handleAsk(question) {
    if (!question || !question.trim()) return;
    lastSql = null;
    lastReasoning = null;
    explainBox.classList.remove("show");
    resultsBody.innerHTML = '<div class="empty-state">Run the query to see results here.</div>';
    analysisBody.innerHTML = '<div class="empty-state">Run the query to see its correctness analysis here.</div>';
    sqlOutput.style.opacity = "0.4";
    sqlOutput.textContent = "Generating…";
    setBtnLoading(askBtn, true, "Generating…");

    try {
      lastSql = await generateSql(question);
      sqlOutput.innerHTML = lastSql;
    } catch (err) {
      sqlOutput.textContent = "";
      resultsBody.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
    } finally {
      sqlOutput.style.opacity = "1";
      setBtnLoading(askBtn, false, "Generate SQL");
    }
  }

  async function handleRun() {
    if (!lastSql) return;
    resultsBody.innerHTML = '<div class="empty-state">Running…</div>';
    analysisBody.innerHTML = '<div class="empty-state">Judging…</div>';
    setBtnLoading(runBtn, true, "Running…");

    try {
      const [results, judgement] = await Promise.all([fetchResults(), fetchJudgement()]);
      renderResults(results.columns, results.rows);
      renderAnalysis(judgement);
    } catch (err) {
      resultsBody.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
      analysisBody.innerHTML = `<div class="empty-state">${escapeHtml(err.message)}</div>`;
    } finally {
      setBtnLoading(runBtn, false, "Run Query");
    }
  }

  async function handleExplain() {
    if (!lastSql) return;
    if (explainBox.classList.contains("show")) {
      explainBox.classList.remove("show");
      return;
    }
    if (lastReasoning == null) {
      explainBox.innerHTML = "Loading…";
      explainBox.classList.add("show");
      try {
        lastReasoning = await fetchReasoning();
      } catch (err) {
        explainBox.innerHTML = escapeHtml(err.message);
        return;
      }
    }
    explainBox.innerHTML = lastReasoning;
    explainBox.classList.add("show");
  }

  function setBtnLoading(btn, isLoading, label) {
    btn.disabled = isLoading;
    btn.textContent = label;
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  function renderAnalysis(judgement) {
    const satisfactory = judgement.verdict !== "unsatisfactory";

    let html = `<div class="verdict-banner ${satisfactory ? "" : "fail"}">
      <div class="v-icon">
        ${
          satisfactory
            ? '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M20 6L9 17l-5-5"/></svg>'
            : '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M18 6L6 18M6 6l12 12"/></svg>'
        }
      </div>
      <div class="v-text">
        <b>${satisfactory ? "Judged satisfactory" : "Judged unsatisfactory"}</b>
        <span>Qwen3-32B</span>
      </div>
    </div>`;

    if (judgement.checks && judgement.checks.length) {
      html += '<div class="check-list">';
      judgement.checks.forEach((check) => {
        html += `<div class="check-row ${check.passed ? "" : "fail"}">
          <div class="c-icon">
            ${
              check.passed
                ? '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5"/></svg>'
                : '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M18 6L6 18M6 6l12 12"/></svg>'
            }
          </div>
          <div class="c-text"><b>${escapeHtml(check.label)}</b><span>${escapeHtml(check.detail)}</span></div>
        </div>`;
      });
      html += "</div>";
    }

    analysisBody.innerHTML = html;
  }

  function renderResults(columns, rows) {
    currentPage = 1;
    renderTable(columns, rows);
  }

  function renderTable(columns, rows) {
    if (!rows.length) {
      resultsBody.innerHTML = '<div class="empty-state">Query returned no rows.</div>';
      return;
    }
    const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    const start = (currentPage - 1) * PAGE_SIZE;
    const pageRows = rows.slice(start, start + PAGE_SIZE);

    let html = '<table class="rtable"><thead><tr>';
    columns.forEach((c) => (html += `<th>${c}</th>`));
    html += "</tr></thead><tbody>";
    pageRows.forEach((row) => {
      html += "<tr>";
      row.forEach((cell, i) => {
        html += i === row.length - 1 ? `<td class="num">${cell}</td>` : `<td>${cell}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table>";

    html += `<div class="results-foot"><span>${rows.length} rows</span><div class="pager">`;
    for (let p = 1; p <= totalPages; p++) {
      html += `<button data-page="${p}" class="${p === currentPage ? "on" : ""}">${p}</button>`;
    }
    html += "</div></div>";

    resultsBody.innerHTML = html;

    resultsBody.querySelectorAll(".pager button").forEach((btn) => {
      btn.addEventListener("click", () => {
        currentPage = Number(btn.dataset.page);
        renderTable(columns, rows);
      });
    });
  }

  /* ---------- schema tree toggle ---------- */
  document.querySelectorAll(".tree-table .t-row").forEach((row) => {
    row.addEventListener("click", () => {
      row.parentElement.classList.toggle("open");
    });
  });
  const firstTable = document.querySelector(".tree-table");
  if (firstTable) firstTable.classList.add("open");

  /* ---------- about page: animated metric bars ---------- */
  document.querySelectorAll(".metric-bar-fill").forEach((el) => {
    const target = el.dataset.value || "0";
    requestAnimationFrame(() => {
      el.style.width = target + "%";
    });
  });
})();
