#!/usr/bin/env node
/**
 * build-pages.mjs — generates the GitHub Pages site for qa-mcp-server.
 *
 * Parses qa_mcp/server.py for `@mcp.tool()` decorated async functions and
 * extracts (tool name, signature, first sentence of docstring). The
 * emitted landing page lists every tool grouped by inferred service
 * (Jira, AWS, Jenkins, GitHub, Webex, Composite) with a "View source" link
 * back to the right line on GitHub.
 *
 * Why a parser instead of importing the server: FastMCP's tool registry
 * lives behind real client initialization (boto3, jira, webex, etc.) that
 * we don't want to require on the CI runner. Static parsing of the file
 * is more than enough — the conventions are tight (one decorator per
 * function, docstring is always the first triple-quoted string).
 *
 * The script is intentionally dependency-free (Node 20+ stdlib only) so
 * it runs in plain GitHub Actions without an install step.
 */

import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SERVER_PY = join(ROOT, "qa_mcp", "server.py");
const PAGES_DIR = join(ROOT, "pages");
const OUT = join(ROOT, "_site");

// Project pages live under <user>.github.io/<repo>/ so absolute links in
// the chrome must be prefixed. Override with PAGES_BASE for local preview.
const PAGES_BASE = process.env.PAGES_BASE ?? "/qa-mcp-server";
const REPO_URL = "https://github.com/DwonnG/qa-mcp-server";
const BRANCH = process.env.PAGES_BRANCH ?? "main";

function ensureDir(dir) {
  mkdirSync(dir, { recursive: true });
}

function resetOutput() {
  if (existsSync(OUT)) {
    rmSync(OUT, { recursive: true, force: true });
  }
  ensureDir(OUT);
}

// Categorize tools by name pattern so the landing page can group them by
// the service they touch. Order matters — first match wins. Webex is
// detected by prefix; everything else falls through to keyword sniffing
// against the verb/noun portion of the function name. The "Composite"
// bucket is for tools that orchestrate two or more services (verify_*).
function categorize(name) {
  if (name.startsWith("webex_")) return "Webex";
  if (name.startsWith("qa_verify_")) return "Composite";
  const tail = name.replace(/^qa_/u, "");
  if (/deploy|environment|api_resources|invoke_internal_api/u.test(tail)) {
    return "AWS";
  }
  if (/build|jenkins|e2e_tests|test_builds/u.test(tail)) {
    return "Jenkins";
  }
  if (/pr_|find_pr|dependabot|find_prs/u.test(tail)) {
    return "GitHub";
  }
  if (
    /generate_test_cases|root_cause|summarize_comments|reproduction_steps|analyze_story|analyze_epic/u.test(
      tail,
    )
  ) {
    return "AI";
  }
  return "Jira";
}

const CATEGORY_ORDER = ["Jira", "AI", "AWS", "Jenkins", "GitHub", "Composite", "Webex"];
const CATEGORY_BLURBS = {
  Jira: "Read and mutate Jira tickets — claim QA, transition status, comment, clone release epics.",
  AI: "Bedrock-backed analysis on top of Jira tickets — test cases, RCA, repro steps, story/epic reviews.",
  AWS: "AWS-side checks — Lambda deployment status across environments, API Gateway invoke/discovery.",
  Jenkins: "Pipeline visibility and triggering — E2E status, recent builds, console tails, custom runs.",
  GitHub: "PR lookups, commit-to-PR mapping, Dependabot alert summaries, ticket→PR search.",
  Composite: "End-to-end QA verification flows that orchestrate Jira + GitHub + AWS + Jenkins in one tool.",
  Webex: "Webex bot operations — list rooms, post messages, summarize conversations with AI.",
};

// Extract every @mcp.tool() decorated async def from the server module.
// FastMCP's pattern in this repo is consistent enough for a regex-based
// pass: each decorator sits on its own line immediately above an
// `async def name(...)` block, and the docstring is the first triple-
// quoted string inside the function body.
function loadTools() {
  if (!existsSync(SERVER_PY)) {
    throw new Error(`Cannot find ${SERVER_PY}`);
  }
  const source = readFileSync(SERVER_PY, "utf8");
  const lines = source.split("\n");
  const tools = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!/^\s*@mcp\.tool\(/u.test(line)) continue;
    // Skip decorator lines until we land on the def. There may be
    // additional decorators in theory, though this repo only uses one.
    let defIdx = i + 1;
    while (defIdx < lines.length && /^\s*@/u.test(lines[defIdx])) {
      defIdx += 1;
    }
    const defLine = lines[defIdx] ?? "";
    const nameMatch = defLine.match(/^\s*async\s+def\s+(\w+)\s*\(/u);
    if (!nameMatch) continue;

    // Pull the function name + 1-based line for a GitHub source link.
    const name = nameMatch[1];
    const lineNumber = defIdx + 1;

    // Find the docstring. Walk forward looking for the first """ after the
    // def's closing paren+colon. Capture content until the matching """.
    let docstring = "";
    for (let k = defIdx + 1; k < Math.min(defIdx + 60, lines.length); k++) {
      const trimmed = lines[k].trimStart();
      if (!trimmed.startsWith('"""')) continue;
      const startContent = trimmed.slice(3);
      const closingOnSameLine = startContent.indexOf('"""');
      if (closingOnSameLine !== -1) {
        docstring = startContent.slice(0, closingOnSameLine).trim();
        break;
      }
      const collected = [startContent];
      for (let m = k + 1; m < lines.length; m++) {
        const mTrim = lines[m].trimEnd();
        const close = mTrim.indexOf('"""');
        if (close !== -1) {
          collected.push(mTrim.slice(0, close));
          break;
        }
        collected.push(lines[m]);
      }
      docstring = collected.join("\n").trim();
      break;
    }

    const firstSentence = docstring
      .split(/\n/u)[0]
      .trim()
      .replace(/\s+/gu, " ");

    tools.push({
      name,
      line: lineNumber,
      description: firstSentence || "(no description)",
      category: categorize(name),
    });
  }

  return tools;
}

function groupByCategory(tools) {
  const buckets = new Map();
  for (const tool of tools) {
    if (!buckets.has(tool.category)) buckets.set(tool.category, []);
    buckets.get(tool.category).push(tool);
  }
  // Stable: walk CATEGORY_ORDER, append any uncategorized buckets at end.
  const ordered = [];
  for (const cat of CATEGORY_ORDER) {
    if (buckets.has(cat)) {
      ordered.push([cat, buckets.get(cat).sort((a, b) => a.name.localeCompare(b.name))]);
      buckets.delete(cat);
    }
  }
  for (const [cat, list] of buckets) {
    ordered.push([cat, list.sort((a, b) => a.name.localeCompare(b.name))]);
  }
  return ordered;
}

function esc(value) {
  return String(value)
    .replace(/&/gu, "&amp;")
    .replace(/</gu, "&lt;")
    .replace(/>/gu, "&gt;")
    .replace(/"/gu, "&quot;")
    .replace(/'/gu, "&#39;");
}

// Tool names are snake_case (e.g. qa_verify_vulnerability_resolved) and
// underscores are not break opportunities for browsers — without a hint,
// CSS would break the name mid-word. Inserting <wbr> after every
// underscore gives the browser preferred break points so a long name
// wraps at underscore boundaries (preserving whole words) and only
// falls back to mid-word breaks if a single segment is still too long.
function nameWithBreaks(name) {
  return esc(name).replace(/_/gu, "_<wbr>");
}

function renderToolCard(tool) {
  const href = `${REPO_URL}/blob/${BRANCH}/qa_mcp/server.py#L${tool.line}`;
  return `
    <a class="suite-card suite-card--idle" href="${esc(href)}" target="_blank" rel="noopener noreferrer">
      <div class="suite-card-head">
        <h3><code>${nameWithBreaks(tool.name)}</code></h3>
        <span class="status-chip status-chip--idle">${esc(tool.category)}</span>
      </div>
      <p class="suite-card-desc">${esc(tool.description)}</p>
      <p class="suite-cta">View source <span class="arrow">&rarr;</span></p>
    </a>
  `;
}

function renderCategorySection(category, tools, index) {
  const num = String(index + 1).padStart(2, "0");
  const blurb = CATEGORY_BLURBS[category] ?? "";
  return `
    <section class="section" id="${esc(category.toLowerCase())}">
      <div class="section-head">
        <p class="eyebrow"><span class="eyebrow-num">${num}</span> ${esc(category)}</p>
        <h2>${esc(category)} tools <span class="section-count">&middot; ${tools.length}</span></h2>
        ${blurb ? `<p class="section-desc">${esc(blurb)}</p>` : ""}
      </div>
      <div class="suite-grid">
        ${tools.map(renderToolCard).join("\n")}
      </div>
    </section>
  `;
}

function renderHeroMetrics(tools, groups) {
  // Use the portfolio's .metrics / .metric* tokens so spacing, borders, and
  // typography match the qa-automation-lab and qa-agent-skills sites.
  return `
    <div class="metrics" aria-label="Server summary">
      <div class="metric">
        <span class="metric-value">${tools.length}</span>
        <span class="metric-label">Tools</span>
      </div>
      <div class="metric">
        <span class="metric-value">${groups.length}</span>
        <span class="metric-label">Services</span>
      </div>
      <div class="metric">
        <span class="metric-value">FastMCP</span>
        <span class="metric-label">stdio + http</span>
      </div>
    </div>
  `;
}

function renderDashboard(tools) {
  const groups = groupByCategory(tools);
  return baseLayout({
    title: "qa-mcp-server",
    body: `
      <header class="hero">
        <div class="hero-inner">
          <div class="hero-intro">
            <span class="status-badge status-badge--ok">
              <span class="status-dot"></span>
              <span>${tools.length} tools across ${groups.length} services</span>
            </span>
          </div>
          <h1 class="hero-title">qa-mcp-server</h1>
          <p class="hero-lead">
            An <a href="https://modelcontextprotocol.io" target="_blank" rel="noopener noreferrer">MCP</a>
            server that puts a QA engineer&rsquo;s daily toolbox &mdash; Jira,
            Jenkins, GitHub, AWS, Webex &mdash; behind a single set of
            structured tool calls so AI coding assistants can drive end-to-end
            release verification.
          </p>
          <div class="hero-actions">
            <a class="btn btn--primary" href="${REPO_URL}" target="_blank" rel="noopener noreferrer">
              <span>View on GitHub</span>
              <span class="btn-aside">main</span>
            </a>
            <a class="btn btn--ghost" href="${REPO_URL}#installation" target="_blank" rel="noopener noreferrer">Install &rarr;</a>
            <a class="btn btn--ghost" href="https://modelcontextprotocol.io" target="_blank" rel="noopener noreferrer">MCP spec &rarr;</a>
          </div>
          ${renderHeroMetrics(tools, groups)}
        </div>
      </header>

      <main id="main">
        ${groups
          .map(([cat, list], i) => renderCategorySection(cat, list, i))
          .join("\n")}

        <section class="section" id="install">
          <div class="section-head">
            <p class="eyebrow"><span class="eyebrow-num">${String(groups.length + 1).padStart(2, "0")}</span> Install</p>
            <h2>Wire it into your MCP client</h2>
          </div>
          <div class="about-card">
            <p>
              The server is published as a public container image on GHCR &mdash;
              no clone, no Python setup. Pull it once, then point your MCP
              client (Cursor, Claude Desktop, etc.) at <code>docker run</code>
              over stdio.
            </p>
            <pre><code>docker pull ghcr.io/dwonng/qa-mcp-server:latest</code></pre>
            <p>
              Add the server to <code>~/.cursor/mcp.json</code> (or your
              Claude Desktop config). Only the credentials you actually use
              need to be set &mdash; missing env vars just disable the
              matching tool group.
            </p>
            <details class="config-toggle">
              <summary>
                <span class="config-toggle-label">Show full MCP client config</span>
                <span class="config-toggle-hint"><code>mcp.json</code> snippet</span>
              </summary>
              <pre><code>{
  "mcpServers": {
    "qa-automation": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "JIRA_URL=https://your-jira.atlassian.net",
        "-e", "JIRA_PERSONAL_TOKEN=your_token",
        "-e", "GITHUB_TOKEN=ghp_your_token",
        "-e", "JENKINS_URL=https://your-jenkins.com",
        "-e", "JENKINS_USER=your_user",
        "-e", "JENKINS_TOKEN=your_token",
        "-e", "AWS_REGION=us-east-1",
        "-e", "WEBEX_TOKEN=your_webex_token",
        "-v", "$HOME/.aws:/root/.aws:ro",
        "-v", "$HOME/.config/qa-mcp-server/config.py:/app/config.py:ro",
        "ghcr.io/dwonng/qa-mcp-server:latest"
      ]
    }
  }
}</code></pre>
            </details>
            <p>
              Mount a <code>config.py</code> (copy from
              <code>config_example.py</code>) for org-specific Jira field
              IDs, Jenkins job paths, and JQL templates. See the
              <a href="${REPO_URL}#readme" target="_blank" rel="noopener noreferrer">README</a>
              for the full env-var matrix, IAM permissions each tool needs,
              and the local Python path if you'd rather run from source.
            </p>
          </div>
        </section>
      </main>

      <footer class="footer">
        <p>
          Built by
          <a href="https://dwonng.github.io" target="_blank" rel="noopener noreferrer">Dwonn Goodwin</a>
          &middot; MIT licensed &middot;
          <a href="${REPO_URL}" target="_blank" rel="noopener noreferrer">source</a>
          &middot; data:
          <a href="${PAGES_BASE}/data/tools.json">tools.json</a>
        </p>
      </footer>
    `,
  });
}

function render404() {
  return baseLayout({
    title: "404 · qa-mcp-server",
    body: `
      <main class="detail" id="main" style="text-align: center">
        <header class="detail-head" style="margin-top: 2rem">
          <p class="eyebrow"><span class="eyebrow-num">404</span> Not found</p>
          <h1>This tool isn&rsquo;t registered</h1>
          <p class="lede" style="margin-left: auto; margin-right: auto; max-width: 50ch">
            The page you were looking for isn&rsquo;t here. The tool catalog
            and the source repo are linked below.
          </p>
          <div class="hero-actions" style="justify-content: center">
            <a class="btn btn--primary" href="${PAGES_BASE}/">Back to catalog</a>
            <a class="btn btn--ghost" href="${REPO_URL}" target="_blank" rel="noopener noreferrer">View on GitHub</a>
          </div>
        </header>
      </main>
    `,
  });
}

function baseLayout({ title, body }) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="color-scheme" content="light dark" />
    <title>${esc(title)}</title>
    <meta name="description" content="qa-mcp-server — MCP tools for QA workflows across Jira, Jenkins, GitHub, AWS, and Webex." />
    <link rel="icon" type="image/svg+xml" href="${PAGES_BASE}/favicon.svg" />
    <meta name="theme-color" content="#0a0a0d" media="(prefers-color-scheme: dark)" />
    <meta name="theme-color" content="#f6f7fa" media="(prefers-color-scheme: light)" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&display=swap"
      rel="stylesheet"
    />
    <script>
      (function () {
        try {
          var saved = localStorage.getItem("theme");
          var systemLight = window.matchMedia("(prefers-color-scheme: light)").matches;
          var theme = saved || (systemLight ? "light" : "dark");
          document.documentElement.setAttribute("data-theme", theme);
        } catch (_) {
          document.documentElement.setAttribute("data-theme", "dark");
        }
      })();
    </script>
    <link rel="stylesheet" href="${PAGES_BASE}/styles.css" />
  </head>
  <body>
    <div class="bg-grid" aria-hidden="true"></div>
    <div class="bg-glow bg-glow--a" aria-hidden="true"></div>
    <div class="bg-glow bg-glow--b" aria-hidden="true"></div>
    <div class="bg-glow bg-glow--c" aria-hidden="true"></div>
    <div class="bg-glow bg-glow--d" aria-hidden="true"></div>

    <a class="skip-link" href="#main">Skip to content</a>

    <nav class="top-nav" aria-label="Site">
      <a class="nav-brand" href="${PAGES_BASE}/">
        <span class="nav-brand-mark" aria-hidden="true">QA</span>
        <span>mcp<span class="nav-brand-full">-server</span></span>
      </a>
      <div class="nav-links">
        <a class="nav-back" href="https://dwonng.github.io/#work"><svg class="nav-back__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>Portfolio</a>
        <a href="${PAGES_BASE}/#jira">Tools</a>
        <a href="${PAGES_BASE}/#install">Install</a>
        <a href="${REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub</a>
      </div>
      <a class="nav-back nav-back--mobile" href="https://dwonng.github.io/#work"><svg class="nav-back__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>Portfolio</a>
      <button
        class="nav-toggle"
        type="button"
        aria-expanded="false"
        aria-controls="mobile-menu"
        aria-label="Open navigation menu"
      >
        <span class="nav-toggle__bar"></span>
        <span class="nav-toggle__bar"></span>
        <span class="nav-toggle__bar"></span>
      </button>
    </nav>

    <div class="mobile-menu" id="mobile-menu" aria-hidden="true">
      <a href="${PAGES_BASE}/#jira">Tools</a>
      <a href="${PAGES_BASE}/#install">Install</a>
      <a href="${REPO_URL}" target="_blank" rel="noopener noreferrer">GitHub</a>
    </div>

    ${body}

    <button class="theme-toggle" type="button" aria-label="Toggle color theme" title="Toggle color theme">
      <svg class="theme-toggle__icon theme-toggle__sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </svg>
      <svg class="theme-toggle__icon theme-toggle__moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
    </button>

    <script src="${PAGES_BASE}/app.js" defer></script>
  </body>
</html>
`;
}

function copyChromeAssets() {
  for (const filename of ["styles.css", "app.js", "favicon.svg"]) {
    const src = join(PAGES_DIR, filename);
    if (!existsSync(src)) {
      throw new Error(`Missing chrome asset: ${src}`);
    }
    cpSync(src, join(OUT, filename));
  }
}

function main() {
  resetOutput();
  const tools = loadTools();
  if (tools.length === 0) {
    throw new Error("No @mcp.tool() decorated functions found — check server.py path");
  }
  copyChromeAssets();
  writeFileSync(join(OUT, "index.html"), renderDashboard(tools));
  writeFileSync(join(OUT, "404.html"), render404());
  ensureDir(join(OUT, "data"));
  writeFileSync(
    join(OUT, "data", "tools.json"),
    JSON.stringify(
      {
        generated_at: new Date().toISOString(),
        repo: REPO_URL,
        count: tools.length,
        tools,
      },
      null,
      2,
    ),
  );
  console.log(`[build-pages] indexed ${tools.length} MCP tools into ${OUT}`);
}

main();
