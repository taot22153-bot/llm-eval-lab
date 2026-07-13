# LLM Eval Lab

Local-first quality and safety evaluation for LLM applications.

> Status: design phase. The product scope and architecture decisions are documented; implementation has not started yet.

## Why this project

Changing a model, system prompt, generation parameter, knowledge source, or tool can improve one behavior while silently breaking another. A single aggregate score is not enough to decide whether an LLM application is safe to release.

LLM Eval Lab is planned as a local Web console that compares a candidate application version with a known baseline, surfaces regressions, and produces an explainable release decision.

## Planned evaluation flow

1. Define immutable baseline and candidate application versions.
2. Run the same versioned evaluation suite against both versions.
3. Combine deterministic checks with local model-based semantic scoring.
4. Route conflicting or low-confidence results to human review.
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
