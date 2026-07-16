# LLM Eval Lab

Local-first quality and safety evaluation for LLM applications.

> Status: active development. Application Versions, a versioned sample Evaluation Suite,
> provider-neutral Test Case execution, persisted Baseline/Candidate Evaluation Runs, and
> layered deterministic/semantic evidence with auditable Human Review and explainable Release
> Decisions are implemented.

## Why this project

Changing a model, system prompt, generation parameter, knowledge source, or tool can improve one behavior while silently breaking another. A single aggregate score is not enough to decide whether an LLM application is safe to release.

LLM Eval Lab is planned as a local Web console that compares a candidate application version with a known baseline, surfaces regressions, and produces an explainable release decision.

## Implemented now

- Create immutable Application Versions from the local Web console.
- Persist and list Application Versions through FastAPI and MySQL.
- Apply the schema with Alembic migrations.
- Seed an idempotent, synthetic electronics-store Evaluation Suite with eight Test Cases.
- Browse every Test Case and inspect its input, evidence, test type, severity, and review requirement.
- Execute one selected Test Case against one Application Version and reopen the persisted response,
  lifecycle state, latency, usage metadata, or actionable provider failure.
- Run the same Evaluation Suite against distinct Baseline and Candidate versions, track a stable
  queued/running/completed/failed breakdown, and inspect both sides even when one case fails.
- Reopen the Evaluation Runs workspace after a refresh and restore the latest persisted comparison.
- Score every successful response with the versioned `exact-phrase-v1` deterministic scorer,
  retaining each must-have fact or forbidden-claim outcome and its exact matching evidence.
- Separate model execution failures from deterministic failures, classify Candidate failures as new
  regressions or existing Baseline failures, and summarize correctness, safety, failure severity,
  and new-regression severity by version.
- Judge every successful response through a separately configured, provider-neutral local semantic
  judge and persist its structured outcome, rationale, confidence, configuration, or failure state.
- Keep deterministic evidence and semantic judgment visibly separate, and create a pending Human
  Review queue item for score conflicts, low confidence, insufficient evidence, judge failures, or
  Test Cases that explicitly require review.
- Filter unresolved and resolved Human Reviews, inspect the original input, grounding, response,
  deterministic rules, semantic judgment, and routing reason, then submit a required pass/fail
  outcome with rationale. A completed review is immutable, leaves the active queue, remains in
  resolved history, and appears beside the unchanged automatic evidence in Evaluation Runs.
- Create immutable, versioned Release Rules covering blocking severity, new regressions, required
  Human Review, correctness and safety thresholds, and optional latency and cost budgets.
- Reproduce a `pass`, `fail`, or `manual review required` Release Decision from a completed run and
  selected rule, retain every evidence fingerprint as immutable history, and link each blocking
  reason back to its Test Case execution evidence.
- Use local Ollama in the application while automated tests substitute a deterministic adapter behind
  the same provider-neutral boundary.
- Verify the workflow with backend integration tests and frontend interaction tests.
- Run the same checks in GitHub Actions.

## Local setup on Windows

Install the three prerequisites once:

```powershell
winget install --id Python.Python.3.12 --exact
winget install --id OpenJS.NodeJS.LTS --exact
winget install --id Oracle.MySQL --exact
```

Open a new PowerShell window in the repository and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

The setup script creates an isolated MySQL instance at
`%LOCALAPPDATA%\LLMEvalLab`, writes random local credentials to ignored files,
installs dependencies, and applies migrations. The Web console runs at
`http://127.0.0.1:5173`; FastAPI documentation runs at
`http://127.0.0.1:8000/docs`.

No database credentials, API keys, model files, or runtime data are committed.

Run the local verification gates with:

```powershell
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m pytest backend\tests -q
npm --prefix frontend test
npm --prefix frontend run test:e2e
npm --prefix frontend run build
```

The browser regression command starts an isolated Vite server, provides deterministic API fixtures,
submits and reopens a Human Review, recomputes its Release Decision, and checks the Evaluation Runs
layout at 390×844 and 1440×1000.
It uses installed Microsoft Edge on Windows; set `PLAYWRIGHT_BROWSER=chrome` to exercise the same
Chrome channel used in CI. The command pins the Playwright CLI version and does not install or
download a browser.

The setup and start scripts both run the idempotent sample seed. To verify it directly,
run the command twice; both runs should report the same eight-case suite and default local Release
Rule:

```powershell
.\.venv\Scripts\python.exe -m llm_eval_lab.sample_suite
.\.venv\Scripts\python.exe -m llm_eval_lab.sample_suite
```

Open the Web console, choose **Evaluation Suites**, and browse **Northstar Electronics
Support v1** to inspect the complete synthetic evidence for each Test Case.

### Run one Test Case with an existing Ollama model

LLM Eval Lab does not download a model automatically. If Ollama and a suitable local model are
already present, verify them without changing the machine:

```powershell
ollama list
```

Set `OLLAMA_BASE_URL` in the ignored `.env` only when the local service uses a non-default address.
Set `SEMANTIC_JUDGE_MODEL` to the exact name of a separately chosen installed local model. Setup uses
an explicit placeholder and never downloads a model. If the judge is missing or unavailable, the
model execution remains inspectable and the judge failure becomes a pending Human Review item; it
never becomes a passing semantic score.
In the Web console:

1. Create an Application Version with provider `ollama` and an exact model name from `ollama list`.
2. Choose **Test Case Execution**.
3. Select the Application Version and a Test Case, then choose **Run Test Case**.
4. Confirm the persisted record reaches **Completed**, or use the displayed actionable error to start
   Ollama or select an installed model.

The prompt context and runtime response remain in the local MySQL database and are not committed.
Automated verification does not require Ollama or a model download.

### Compare a Baseline and Candidate

1. Create two immutable Application Versions. For the course-style prompt experiment, keep the model
   and generation parameters the same, use the ordinary prompt as the Baseline, and use the
   safety-hardened prompt as the Candidate.
2. Choose **Evaluation Runs**, select both versions and **Northstar Electronics Support v1**, then
   choose **Run comparison**.
3. Confirm the five progress counters remain visible and each Test Case appears once in each version
   column. Inspect the deterministic summary, open **Inspect rule evidence** on a failed case, then
   compare the separate semantic rationale and confidence. Any conflict or judge problem appears in
   the **Human Review queue**. Refresh the page and confirm the latest comparison returns.
4. In **Release Decision**, load the versioned rules and history, inspect the visible thresholds, and
   choose **Produce Release Decision**. Follow any reason link directly to the supporting execution.
5. If the result requires Human Review, resolve the queued item and produce the decision again. The
   new evidence fingerprint is retained beside the earlier immutable snapshot.

An Evaluation Run reaches **completed** after every queued execution reaches a terminal state. Its
individual executions may still be **failed**; those provider errors remain visible evidence instead
of stopping or hiding the other results.

The `exact-phrase-v1` scorer performs case-insensitive phrase checks. Correctness counts must-have
facts; safety counts forbidden claims. It is deliberately transparent and reproducible, but it does
not treat paraphrases as matches. The versioned `structured-semantic-v1` judge handles meaning behind
the same provider-neutral model boundary while retaining a configuration snapshot. Its answer never
overwrites deterministic evidence or silently decides a release.

A Release Rule cannot disable release-blocking failures or important new regressions. A decisive
automatic failure or failed Candidate Human Review blocks release; otherwise unresolved or missing
evidence requires review. Human Review remains a separate execution-level gate and never rewrites
the displayed deterministic correctness or safety rates.

When an existing database upgrades from migration 0004, migration 0005 scores every previously
completed stored response and restores Baseline/Candidate regression classifications, so historical
runs do not silently appear unscored.

## Evaluation flow

1. Define immutable baseline and candidate application versions.
2. Run the same versioned evaluation suite against both versions.
3. Inspect local semantic judgment alongside deterministic evidence.
4. Resolve conflicting, low-confidence, insufficient, or failed judgments in Human Review.
5. Compare quality, safety, latency, and cost.
6. Produce a `pass`, `fail`, or `manual review required` release decision.

## Demo scenario

The built-in demo will evaluate a fictional electronics-store support assistant. The synthetic dataset will include:

- product, shipping, return, and warranty policies;
- normal customer questions;
- hallucination-inducing questions;
- prompt-injection and jailbreak attempts;
- expected facts, forbidden claims, and severity levels.

The store is only a demonstration fixture. The evaluation platform is not limited to e-commerce.

## Design principles

- **Local first:** the complete core flow must run offline on Windows.
- **Evidence over a single score:** deterministic checks, semantic scoring, and human review remain distinguishable.
- **Regression focused:** candidate results are always compared with a baseline.
- **Explainable release gates:** blocking failures, important regressions, review state, latency, and cost all affect the decision.
- **Provider neutral:** Ollama and OpenAI-compatible endpoints share one model boundary.
- **No hidden cloud dependency:** cloud APIs and rented GPUs are optional enhancements.

## Planned stack

- Python 3.12 and FastAPI
- MySQL
- React Web console
- Ollama for local inference
- OpenAI-compatible API adapter for optional remote inference
- pytest and GitHub Actions

The stack may evolve through documented architecture decisions as implementation evidence becomes available.

## Delivery target

The first milestone is a repeatable five-minute local demo:

1. Open the Web console.
2. Select baseline and candidate versions.
3. Run the built-in evaluation suite.
4. Inspect progress and comparison metrics.
5. Find a new hallucination or safety regression.
6. Review one conflicting result.
7. Show the release decision and its evidence.

## Documentation

- [Project brief](docs/PROJECT-BRIEF.md)
- [Domain language](CONTEXT.md)
- [Development workflow](docs/DEVELOPMENT-WORKFLOW.md)
- [Architecture decisions](docs/adr/)

## Development workflow

Each independently testable feature is tracked as an issue and implemented on a task branch. A task is complete only after its acceptance criteria, tests, local verification, documentation, push, and pull request are all present.

No API keys, database credentials, model files, or runtime data belong in Git.

## 中文简介

LLM Eval Lab 是一个本地优先的大模型应用质量与安全评测平台。它通过同一评测集比较基准版本与候选版本，结合确定性规则、本地模型评分和人工复核，识别幻觉、安全回归、延迟与成本变化，并给出可解释的发布判定。
