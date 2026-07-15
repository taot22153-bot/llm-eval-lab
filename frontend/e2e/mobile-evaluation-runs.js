async (page) => {
  const versions = [
    {
      id: "baseline-version",
      name: "Mobile baseline",
      model_provider: "fixture",
      model_name: "deterministic",
      system_prompt: "Answer from evidence.",
      generation_parameters: { temperature: 0 },
      knowledge_config: null,
      tool_config: null,
      created_at: "2026-07-15T00:00:00Z",
    },
    {
      id: "candidate-version",
      name: "Mobile candidate",
      model_provider: "fixture",
      model_name: "deterministic",
      system_prompt: "Reject unsafe instructions and answer from evidence.",
      generation_parameters: { temperature: 0 },
      knowledge_config: null,
      tool_config: null,
      created_at: "2026-07-15T00:00:01Z",
    },
  ];
  const suite = {
    id: "mobile-suite",
    slug: "mobile-regression",
    version: 1,
    name: "Mobile Regression Fixture",
    description: "Browser-only responsive regression data.",
    test_case_count: 1,
    test_type_counts: {
      normal: 1,
      hallucination: 0,
      prompt_injection: 0,
      jailbreak: 0,
    },
    severity_counts: { normal: 1, important: 0, release_blocking: 0 },
  };
  const suiteDetail = {
    ...suite,
    test_cases: [
      {
        id: "mobile-case",
        key: "mobile-case",
        position: 1,
        title: "Keep all progress evidence readable",
        user_input: "Summarize the policy.",
        grounding_material: [],
        must_have_facts: [],
        forbidden_claims: [],
        test_type: "normal",
        severity: "normal",
        requires_human_review: false,
      },
    ],
  };
  const execution = (role) => ({
    id: `${role}-execution`,
    application_version_id: `${role}-version`,
    application_version_name: role === "baseline" ? "Mobile baseline" : "Mobile candidate",
    test_case_id: "mobile-case",
    test_case_key: "mobile-case",
    test_case_title: "Keep all progress evidence readable",
    test_case_severity: "normal",
    status: "completed",
    prompt_context: {
      system_prompt: "Answer from evidence.",
      grounding_material: [],
      user_input: "Summarize the policy.",
    },
    model_response: "Persisted response evidence.",
    usage: { prompt_tokens: 10, completion_tokens: 4, total_tokens: 14 },
    latency_ms: 5,
    error: null,
    deterministic_evaluation: {
      scorer_version: "exact-phrase-v1",
      passed: true,
      regression_classification: null,
      outcomes: [
        {
          check_type: "must_have_fact",
          position: 1,
          rule: "Persisted response evidence.",
          passed: true,
          matched_evidence: "Persisted response evidence.",
        },
      ],
    },
    semantic_evaluation: {
      judge_version: "structured-semantic-v1",
      outcome: role === "baseline" ? "pass" : "fail",
      rationale: role === "baseline"
        ? "The answer is supported by the fixture evidence."
        : "The candidate meaning conflicts with the deterministic result.",
      confidence: 0.91,
      judge_configuration: {
        judge_version: "structured-semantic-v1",
        provider: "fixture-judge",
        model: "responsive-judge-v1",
        generation_parameters: { temperature: 0 },
        low_confidence_threshold: 0.7,
      },
      error: null,
      created_at: "2026-07-15T00:00:00Z",
    },
    human_review_item: role === "candidate" ? {
      id: "mobile-review",
      status: "pending",
      reasons: ["automatic_conflict"],
      outcome: null,
      rationale: null,
      created_at: "2026-07-15T00:00:00Z",
      resolved_at: null,
    } : null,
    version_role: role,
    created_at: "2026-07-15T00:00:00Z",
    started_at: "2026-07-15T00:00:00Z",
    completed_at: "2026-07-15T00:00:00.005Z",
  });
  const emptyVersionSummary = {
    scored_test_cases: 1,
    passed_test_cases: 1,
    failed_test_cases: 0,
    correctness: { passed: 0, failed: 0, total: 0 },
    safety: { passed: 0, failed: 0, total: 0 },
    severity_failures: { normal: 0, important: 0, release_blocking: 0 },
  };
  const singleExecution = {
    ...execution("baseline"),
    id: "single-execution",
    semantic_evaluation: {
      judge_version: "structured-semantic-v1",
      outcome: null,
      rationale: null,
      confidence: null,
      judge_configuration: {
        judge_version: "structured-semantic-v1",
        provider: "ollama",
        model: "missing-local-judge",
        generation_parameters: { temperature: 0 },
        low_confidence_threshold: 0.7,
      },
      error: {
        code: "provider_unavailable",
        message: "Cannot reach the configured local semantic judge.",
      },
      created_at: "2026-07-15T00:00:00Z",
    },
    human_review_item: {
      id: "single-review",
      status: "pending",
      reasons: ["judge_failure"],
      outcome: null,
      rationale: null,
      created_at: "2026-07-15T00:00:00Z",
      resolved_at: null,
    },
  };
  const run = {
    id: "mobile-run",
    baseline_version: { id: versions[0].id, name: versions[0].name },
    candidate_version: { id: versions[1].id, name: versions[1].name },
    evaluation_suite: {
      id: suite.id,
      slug: suite.slug,
      version: suite.version,
      name: suite.name,
    },
    status: "completed",
    progress: { total: 2, queued: 0, running: 0, completed: 2, failed: 0 },
    deterministic_summary: {
      baseline: emptyVersionSummary,
      candidate: emptyVersionSummary,
      new_regressions: 0,
      new_regressions_by_severity: { normal: 0, important: 0, release_blocking: 0 },
      existing_failures: 0,
    },
    executions: [execution("baseline"), execution("candidate")],
    created_at: "2026-07-15T00:00:00Z",
    started_at: "2026-07-15T00:00:00Z",
    completed_at: "2026-07-15T00:00:01Z",
  };
  const reviewItems = [
    {
      id: "mobile-review",
      test_case_execution_id: "candidate-execution",
      test_case_title: "Keep all progress evidence readable",
      application_version_name: "Mobile candidate",
      evaluation_run_id: run.id,
      version_role: "candidate",
      status: "pending",
      reasons: ["automatic_conflict"],
      outcome: null,
      rationale: null,
      created_at: "2026-07-15T00:00:00Z",
      resolved_at: null,
    },
  ];
  let reviewResolved = false;
  const reviewRationale = "The semantic evidence justifies passing this response.";
  const reviewDetail = (resolved) => ({
    ...reviewItems[0],
    status: resolved ? "resolved" : "pending",
    outcome: resolved ? "pass" : null,
    rationale: resolved ? reviewRationale : null,
    resolved_at: resolved ? "2026-07-15T00:05:00Z" : null,
    execution: {
      ...execution("candidate"),
      human_review_item: {
        ...execution("candidate").human_review_item,
        status: resolved ? "resolved" : "pending",
        outcome: resolved ? "pass" : null,
        rationale: resolved ? reviewRationale : null,
        resolved_at: resolved ? "2026-07-15T00:05:00Z" : null,
      },
    },
  });

  const consoleIssues = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => consoleIssues.push(`pageerror: ${error.message}`));
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const requestUrl = route.request().url();
    const pathname = requestUrl.slice(requestUrl.indexOf("/api/")).split("?")[0];
    let body;
    if (pathname === "/api/application-versions") body = versions;
    else if (pathname === "/api/evaluation-suites") body = [suite];
    else if (pathname === `/api/evaluation-suites/${suite.id}`) body = suiteDetail;
    else if (pathname === "/api/evaluation-runs") body = [run];
    else if (pathname === "/api/human-review-items") {
      body = requestUrl.includes("status=resolved")
        ? (reviewResolved ? [reviewDetail(true)] : [])
        : (reviewResolved ? [] : reviewItems);
    }
    else if (pathname === "/api/human-review-items/mobile-review") {
      if (request.method() === "PATCH") reviewResolved = true;
      body = reviewDetail(reviewResolved);
    }
    else if (pathname === "/api/test-case-executions") body = singleExecution;
    else body = { detail: `Unexpected browser fixture request: ${pathname}` };
    await route.fulfill({
      status: body.detail ? 404 : 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });

  async function assertViewport(width, height, expectedColumns) {
    await page.setViewportSize({ width, height });
    const measurements = await page.evaluate(() => {
      const root = document.documentElement;
      const progress = document.querySelector(".comparison-progress");
      const cards = [...document.querySelectorAll(".progress-card")];
      const navigationButtons = [...document.querySelectorAll(".primary-navigation button")];
      return {
        documentClientWidth: root.clientWidth,
        documentScrollWidth: root.scrollWidth,
        progressColumns: progress
          ? getComputedStyle(progress).gridTemplateColumns.trim().split(/\s+/).length
          : 0,
        overflowingProgressLabels: cards
          .filter((card) => card.scrollWidth > card.clientWidth)
          .map((card) => card.textContent?.trim()),
        navigationButtons: navigationButtons.map((button) => {
          const rect = button.getBoundingClientRect();
          return {
            label: button.textContent?.trim(),
            visible: rect.width > 0 && rect.height > 0,
            insideViewport: rect.left >= 0 && rect.right <= root.clientWidth,
          };
        }),
      };
    });
    if (measurements.documentScrollWidth !== measurements.documentClientWidth) {
      throw new Error(`Document overflow at ${width}px: ${JSON.stringify(measurements)}`);
    }
    if (measurements.progressColumns !== expectedColumns) {
      throw new Error(`Expected ${expectedColumns} progress columns at ${width}px: ${JSON.stringify(measurements)}`);
    }
    if (measurements.overflowingProgressLabels.length > 0) {
      throw new Error(`Progress labels overflow at ${width}px: ${JSON.stringify(measurements)}`);
    }
    if (
      measurements.navigationButtons.length !== 4
      || measurements.navigationButtons.some((button) => !button.visible || !button.insideViewport)
    ) {
      throw new Error(`Primary navigation is not fully usable at ${width}px: ${JSON.stringify(measurements)}`);
    }
  }

  await page.goto("http://127.0.0.1:5173");
  await page.getByRole("heading", { name: "Application Versions" }).waitFor();
  await page.getByRole("button", { name: "Evaluation Runs" }).click();
  await page.getByText("Latest persisted run").waitFor();
  await page.getByRole("region", { name: "Human Review queue" }).waitFor();
  await page.getByText("1 unresolved").waitFor();
  await page.getByText("Semantic fail").waitFor();
  await assertViewport(390, 844, 3);
  await assertViewport(1440, 1000, 5);
  const reviewQueue = page.getByRole("region", { name: "Human Review queue" });
  const reviewButtonName = "Review Keep all progress evidence readable for Mobile candidate (candidate, run mobile-run)";
  await reviewQueue.getByRole("button", { name: reviewButtonName }).click();
  const reviewPanel = page.getByRole("region", { name: "Human Review detail" });
  await reviewPanel.getByText("Summarize the policy.").waitFor();
  await reviewPanel.locator(".human-review-detail__context")
    .getByText("Persisted response evidence.", { exact: true }).waitFor();
  await reviewPanel.getByText("Deterministic pass").waitFor();
  await reviewPanel.getByText("Scorer exact-phrase-v1").waitFor();
  await reviewPanel.getByText("Matched response: Persisted response evidence.").waitFor();
  await reviewPanel.getByText("Semantic fail").waitFor();
  await reviewPanel.getByText("Automatic score conflict", { exact: true }).waitFor();
  await reviewPanel.getByLabel("Human outcome").selectOption("pass");
  await reviewPanel.getByLabel("Review rationale").fill(reviewRationale);
  await reviewPanel.getByRole("button", { name: "Submit Human Review" }).click();
  await reviewPanel.getByText("Human review pass").waitFor();
  await reviewPanel.getByText(reviewRationale).waitFor();
  await reviewQueue.getByText("0 unresolved").waitFor();
  await reviewQueue.getByRole("button", { name: "Resolved history" }).click();
  await reviewQueue.getByRole("button", { name: "Resolved history (1)" }).waitFor();
  await reviewQueue.getByRole("button", { name: reviewButtonName }).click();
  const reopenedReview = page.getByRole("region", { name: "Human Review detail" });
  await reopenedReview.getByText("Human review pass").waitFor();
  await reopenedReview.getByText(reviewRationale).waitFor();
  await reopenedReview.getByText("Deterministic pass").waitFor();
  await reopenedReview.getByText("Semantic fail").waitFor();
  await reopenedReview.getByText("Matched response: Persisted response evidence.").waitFor();
  await assertViewport(390, 844, 3);
  await assertViewport(1440, 1000, 5);
  await page.getByRole("button", { name: "Test Case Execution" }).click();
  await page.getByRole("button", { name: "Run Test Case" }).click();
  await page.getByText("Semantic judge failed").waitFor();
  await page.getByText("Pending human review").waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  const singleExecutionWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  if (singleExecutionWidth.client !== singleExecutionWidth.scroll) {
    throw new Error(`Single execution overflow: ${JSON.stringify(singleExecutionWidth)}`);
  }
  if (consoleIssues.length > 0) {
    throw new Error(`Browser console issues: ${consoleIssues.join("\n")}`);
  }
}
