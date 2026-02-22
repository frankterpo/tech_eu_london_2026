# 🧾 Invoice 1-Shot CLI

**One prompt. One invoice. Zero manual clicks.**

Invoice 1-Shot is a self-healing agent orchestration CLI designed to automate complex workflows on legacy invoicing platforms (like Envoice). Built during the **Tech EU London 2026 Hackathon**, it bridges the gap between natural language intent and brittle legacy UIs using a "Mine-Orchestrate-Heal" loop.

🌐 **Landing Page:** [https://invoice1shot.lovable.app](https://invoice1shot.lovable.app)

---

## 🚀 The "Holy Shit" Moment

1. **Natural Language Intent:** You type `agent ask "Invoice ACME Corp for $32k"`.
2. **Dust.tt Orchestration:** A **Dust.tt** agent (powered by **Gemini 1.5 Pro**) routes your prompt to the correct "Skill" and extracts structured data.
3. **Local Playwright Execution:** The CLI launches a browser, uses your captured session, and executes the clicks/fills.
4. **Self-Healing Loop:** If the legacy UI has changed, the agent captures a trace, **Gemini Vision** analyzes the failure, and Dust.tt applies an **RFC6902 JSON Patch** to fix the skill automatically for the next run.

---

## 🛠 Partner Technologies (Min. 3 Used)

We heavily utilized the following partner stacks to power our agent:

1.  **[Dust.tt](https://dust.tt)**: Used as the primary **Agent Orchestrator**. We use the Dust programmatic API to handle Routing, Evaluation, and Workflow Mining.
2.  **[Google Gemini](https://deepmind.google/technologies/gemini/)**: Powers the reasoning engine within Dust.tt. **Gemini 1.5 Pro** handles complex routing, while **Gemini Vision** evaluates browser screenshots to diagnose UI failures.
3.  **[Supabase](https://supabase.com)**: Our backend source of truth.
    *   **Postgres**: Stores `skills`, `runs`, and a live `events` audit trail for QA.
    *   **Storage**: Stores encrypted Playwright `auth` states and execution artifacts (videos, traces, screenshots).
4.  **[Lovable](https://lovable.app)**: Used to build our **Landing Page** and user-facing dashboard. It provides a seamless interface for users to discover the CLI tool and view project documentation.

---

## 📦 Installation & Setup

### Prerequisites
- Python 3.9+
- Node.js (for Supabase CLI)
- Playwright browsers

### 1. Clone & Install
```bash
git clone https://github.com/frankterpo/tech_eu_london_2026
cd tech_eu_london_2026
make install
```
`make install` installs the CLI and Playwright Chromium.  
If you are in a restricted CI/sandbox, you can skip browser install:
```bash
SKIP_PLAYWRIGHT_INSTALL=1 make install
```

### 2. Environment Setup
Create a `.env` file in the root based on `.env.template`:
```bash
cp .env.template .env
# Required for app runtime:
# - DUST_API_KEY
# - DUST_WORKSPACE_ID
# - GEMINI_API_KEY (or GOOGLE_API_KEY)
# - SUPABASE_URL
# - SUPABASE_SERVICE_ROLE_KEY (preferred) or SUPABASE_ANON_KEY
#
# Required for Supabase CLI commands:
# - SUPABASE_ACCESS_TOKEN
```

### 3. Bootstrap
```bash
agent bootstrap
make smoke-cloud  # Verify all APIs are connected
```

---

## 🕹 Usage Guide

### Step 1: Capture Authentication
Legacy systems often have complex MFA. Capture your session once locally:
```bash
agent auth save envoice
```

### Step 2: Mine a Workflow
Record yourself performing an action to create a new "Skill":
```bash
agent mine envoice.mimic.foundation_20260222 --headed --max-minutes 20
```

### Step 3: Extrapolate a New Skill from Platform Memory
Generate a new SkillSpec from `.state/platform_maps/envoice.json`:
```bash
agent extrapolate "Create a quarterly sales invoice for ACME for 5000 EUR" \
  --platform-id envoice \
  --skill-id envoice.auto.quarterly_v1
```

### Step 4: Execute via Natural Language
Run one-shot orchestration with auto-acquire + learn/patch loop:
```bash
agent ask "Create a sales invoice for ACME Corp, LLC for 32000 USD" --yes
```

### Step 5: Reliability Gate (Benchmark)
Run repeated execution/evaluation and fail if success rate is below threshold:
```bash
agent benchmark envoice.sales_invoice.existing \
  --input-file .state/bench_inputs/invoice_smoke.json \
  --runs 3 \
  --min-success-rate 0.67 \
  --stop-on-failure
```

### Step 6: Multi-Agent Swarm (Learning First)
Default swarm mode is `learn` (skill generation only; no invoice creation):
```bash
agent swarm \
  --prompt "Create monthly invoice workflow for EU customer with VAT" \
  --prompt "Create purchase invoice workflow with supplier reference" \
  --workers 2 \
  --headless
```

Use `--mode execute` only when you explicitly want workers to run invoice flows:
```bash
agent swarm --mode execute --prompt "Create invoice for ACME 100 EUR" --workers 2
```

### Step 7: Verify Supabase Storage Paths
Check seeds/auth/run artifacts visibility:
```bash
agent storage-check
agent storage-check --run-id <run_uuid>
```

### Optional: Classic Self-Healing Loop
Run route -> run -> eval -> patch iterations:
```bash
agent loop "Create a sales invoice..." --iters 3
```

---

## 📊 Technical Documentation

### System Architecture
- **CLI**: Built with `Typer` and `Rich` for a high-end terminal UX.
- **Executor**: Raw `Playwright` with full video/trace recording enabled.
- **Orchestration**: `DustClient` communicates with Dust.tt programmatic conversations.
- **Platform Learning Memory**: Real mimic sessions are aggregated into `.state/platform_maps/<platform>.json`.
- **Skill Synthesis Pipeline**: Multi-agent map/planner/writer/critic chain with deterministic fallback.
- **Reliability Gate**: Strict evaluator + benchmark command prevent false positive success.
- **Audit Trail**: Events + runs are logged to Supabase for QA monitoring.

### Database Schema
- `skills`: Versioned JSON specs of browser actions (synced from mined/synthesized seeds).
- `runs`: History of every execution, linked to video/trace artifacts.
- `events`: System-wide audit log (e.g., `route_identified`, `skill_patched`).

### Storage Layout (Supabase)
- `auth/<name>.json`: Playwright authenticated storage state.
- `artifacts/seeds/<skill_id>.json`: Seeded/generated skills.
- `artifacts/runs/<run_id>/...`: Run artifacts (run report, trace/video/screenshots when available).
- `artifacts/evals/<run_id>.json`: Evaluation outputs.

---

## 🏆 Hackathon Submission
- **Created:** Newly created at Tech EU London 2026.
- **Team Size:** 1 (Francisco Terpolilli).
- **Partner Tech:** Dust.tt, Google Gemini, Supabase, Lovable.
- **Video Demo:** [Watch the 2-min demo on Loom](https://www.loom.com/share/a5d23850395342e8a05081f9c214d11a)
