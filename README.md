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
# Add your DUST_API_KEY, GEMINI_API_KEY, and SUPABASE_URL
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
agent mine --name create_invoice
```

### Step 3: Run the Orchestrator
Execute a 1-shot invoice creation from natural language:
```bash
agent ask "Create a sales invoice for ACME Corp, LLC for 32000 USD"
```

### Step 4: The Training Loop
Run the self-healing loop to perfect a skill through repetition:
```bash
agent loop "Create a sales invoice..." --iters 3
```

---

## 📊 Technical Documentation

### System Architecture
- **CLI**: Built with `Typer` and `Rich` for a high-end terminal UX.
- **Executor**: Raw `Playwright` with full video/trace recording enabled.
- **Orchestration**: `DustClient` communicates with Dust.tt programmatic conversations.
- **Audit Trail**: Every action is logged to the `events` table in Supabase for real-time QA monitoring.

### Database Schema
- `skills`: Versioned JSON specs of browser actions.
- `runs`: History of every execution, linked to video/trace artifacts.
- `events`: System-wide audit log (e.g., `route_identified`, `skill_patched`).

---

## 🏆 Hackathon Submission
- **Created:** Newly created at Tech EU London 2026.
- **Team Size:** 1 (Francisco Terpolilli).
- **Partner Tech:** Dust.tt, Google Gemini, Supabase, Lovable.
- **Video Demo:** [Watch the 2-min demo on Loom](https://www.loom.com/share/a5d23850395342e8a05081f9c214d11a)
