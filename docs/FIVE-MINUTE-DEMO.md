# Five-minute Windows demo

This is the repeatable interview path for LLM Eval Lab. It uses an explicit deterministic fixture,
so it works without Ollama, a model download, internet access, credentials, or paid APIs. The
fixture proves the platform workflow; it is not presented as a real LLM result.

## One-time prerequisites

From PowerShell in the repository root, install Python 3.12, Node.js LTS, and MySQL 8.4, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1
```

Setup creates an isolated MySQL runtime under `%LOCALAPPDATA%\LLMEvalLab`, stores random local
credentials only in ignored files, installs the project dependencies, and applies all migrations.

## Reset and start

Run this before the interview:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-demo.ps1
```

The command ensures these two reserved Application Version IDs and resets only comparison evidence
where that exact pair is used together:

- `00000000-0000-4000-8000-000000000011` — known Baseline fixture;
- `00000000-0000-4000-8000-000000000012` — Candidate fixture with one known safety regression.

The versioned Northstar suite and default Release Rule are idempotently seeded. Unrelated
Application Versions and their evidence are retained. The Web console opens at
`http://127.0.0.1:5173`; API docs are at `http://127.0.0.1:8000/docs`.

Use reset-only when the services are already running:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reset-demo.ps1
```

Use `scripts\start-demo.ps1 -KeepEvidence` only when you want to show the existing immutable
decision history instead of starting clean.

## Timed interview path

### 0:00–0:40 — frame the problem

Say: “An LLM change is an application-version change: model, prompt, parameters, knowledge, and
tools. I compare the immutable Candidate against an immutable Baseline on the same versioned
Evaluation Suite, rather than trusting a single score.”

Open **Evaluation Runs** and select these records:

- Baseline: **Northstar demo Baseline (deterministic fixture)**;
- Candidate: **Northstar demo Candidate (known safety regression)**;
- suite: **Northstar Interview Demo v1**.

### 0:40–1:30 — run and watch persisted progress

Choose **Run comparison**. Point to queued, running, completed, and failed counters while the
polling view changes. The focused interview Suite contains one Test Case, so the terminal run has
two persisted executions: one for each version.

### 1:30–2:30 — inspect the regression evidence

Find **1 new regression**, then the Candidate execution **Resist a prompt-injection request**.
Open **Inspect rule evidence** and show:

- the Baseline passed the same Test Case;
- the Candidate response contains the exact forbidden claim;
- the severity is **Release blocking**;
- the transparent deterministic result remains separate from the semantic result.

The fixture semantic judge deliberately returns a high-confidence pass, creating a visible
automatic-score conflict. This demonstrates routing, not the quality of a model judge.

### 2:30–3:35 — make the Human Review auditable

In **Human Review queue**, open the Candidate item. Show the original user input, grounding
material, response, matched forbidden claim, semantic rationale, and routing reason. Select
**Fail**, enter a short rationale such as:

```text
The Candidate exposes forbidden prompt-injection content.
```

Choose **Submit Human Review**. Show that unresolved becomes zero, the automatic layers remain
unchanged, and the immutable reviewer decision appears in **Resolved history**.

### 3:35–4:35 — produce the release gate

In **Release Decision**, choose **Load Release Decision**, keep **Default local release rule v1**,
and choose **Produce Release Decision**. Show:

- the decision is **Fail**;
- Candidate safety is 0% while Baseline safety is 100% for the blocking case;
- the reason names the blocking Test Case and links to **Execution evidence**;
- the evidence fingerprint and immutable snapshot count make the decision reproducible.

### 4:35–5:00 — close with the architecture

Say: “The boundary is provider-neutral, but every result is local and evidence-backed. Execution,
deterministic rules, semantic judgment, Human Review, and Release Decision are separate persisted
layers, so a probabilistic judge cannot silently overwrite literal safety evidence.”

```text
Application Versions + versioned Suite
                 │
                 ▼
        persisted Evaluation Run
                 │
        ┌────────┴────────┐
        ▼                 ▼
deterministic rules   semantic judge
        └────────┬────────┘
                 ▼
        conflict routing / Human Review
                 │
                 ▼
      versioned Rule → immutable Decision
```

## Manual Ollama variation

This variation is optional and is not part of deterministic acceptance. LLM Eval Lab never
downloads a model automatically. If Ollama and a suitable model are already installed:

```powershell
ollama list
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Use an exact installed model name when creating each `ollama` Application Version. In the ignored
`.env`, set `SEMANTIC_JUDGE_PROVIDER=ollama` and `SEMANTIC_JUDGE_MODEL` to an exact, separately
chosen installed model. A missing service or model is recorded as actionable provider/judge
failure evidence and must not be described as a successful manual validation.

An OpenAI-compatible remote provider is not implemented in the core demo. It remains an optional
enhancement and the release path has no cloud dependency.

## Troubleshooting

- **Missing `.env`, Python, Node.js, or MySQL runtime:** rerun `scripts\setup-local.ps1` in a new
  PowerShell window.
- **MySQL 3307 does not start:** inspect `%LOCALAPPDATA%\LLMEvalLab\mysql-error.log` and confirm no
  other process owns port 3307.
- **API 8000 or Web 5173 is already in use:** stop the old LLM Eval Lab process, then rerun the
  start command. The scripts do not kill unrelated processes.
- **The demo starts with old history:** omit `-KeepEvidence`, or run `scripts\reset-demo.ps1`.
- **Ollama failure:** verify `ollama list`, the local service, `OLLAMA_BASE_URL`, and the exact model
  name. Do not download a model during the interview unless explicitly approved beforehand.

## Privacy and repository hygiene

Prompts, responses, reviewer rationales, and decision snapshots stay in local MySQL. `.env`, local
database files, logs, model files, Playwright sessions, and runtime artifacts are ignored and must
not be committed. The two PNGs under `docs/screenshots` are synthetic browser-fixture evidence and
contain no user data or credentials.
