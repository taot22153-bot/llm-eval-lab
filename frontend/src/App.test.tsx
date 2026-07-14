import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const createdVersion = {
  id: "6a740412-c0de-4f7e-b538-46226b216e51",
  name: "Store support baseline",
  model_provider: "ollama",
  model_name: "qwen3:8b",
  system_prompt: "Answer only from the supplied store policies.",
  generation_parameters: { temperature: 0.1 },
  knowledge_config: null,
  tool_config: null,
  created_at: "2026-07-13T10:30:00Z",
};

const configuredVersion = {
  ...createdVersion,
  knowledge_config: { source: "sample-store-policies-v1" },
  tool_config: { allowed_tools: ["lookup_order"] },
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Application Versions", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(createdVersion, 201));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("creates an Application Version and shows it immediately", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("No Application Versions yet.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Version name"), createdVersion.name);
    await user.type(screen.getByLabelText("Model provider"), createdVersion.model_provider);
    await user.type(screen.getByLabelText("Model name"), createdVersion.model_name);
    await user.type(screen.getByLabelText("System prompt"), createdVersion.system_prompt);
    await user.clear(screen.getByLabelText("Generation parameters (JSON)"));
    await user.click(screen.getByLabelText("Generation parameters (JSON)"));
    await user.paste(JSON.stringify(createdVersion.generation_parameters));
    await user.click(screen.getByRole("button", { name: "Create version" }));

    expect(await screen.findByText(createdVersion.name)).toBeInTheDocument();
    expect(screen.getByText(createdVersion.model_name)).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/application-versions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: createdVersion.name,
          model_provider: createdVersion.model_provider,
          model_name: createdVersion.model_name,
          system_prompt: createdVersion.system_prompt,
          generation_parameters: createdVersion.generation_parameters,
          knowledge_config: null,
          tool_config: null,
        }),
      });
    });
  });

  it("shows Application Versions persisted before the page loads", async () => {
    fetchMock.mockReset().mockResolvedValueOnce(jsonResponse([createdVersion]));

    render(<App />);

    expect(await screen.findByText(createdVersion.name)).toBeInTheDocument();
    expect(screen.getByText(createdVersion.model_name)).toBeInTheDocument();
    expect(screen.getByText("Immutable")).toBeInTheDocument();
    expect(screen.getByText("1 total")).toBeInTheDocument();
  });

  it("shows every persisted configuration field", async () => {
    const user = userEvent.setup();
    fetchMock.mockReset().mockResolvedValueOnce(jsonResponse([configuredVersion]));

    render(<App />);

    expect(await screen.findByText(configuredVersion.name)).toBeInTheDocument();
    await user.click(screen.getByText("Configuration"));

    expect(screen.getByText("Knowledge config")).toBeInTheDocument();
    expect(screen.getByText(/sample-store-policies-v1/)).toBeInTheDocument();
    expect(screen.getByText("Tool config")).toBeInTheDocument();
    expect(screen.getByText(/lookup_order/)).toBeInTheDocument();
  });

  it("creates a second version instead of editing an existing version", async () => {
    const user = userEvent.setup();
    const candidateVersion = {
      ...createdVersion,
      id: "01888f39-3a8a-7a15-88e8-c63b9e4eb497",
      name: "Store support candidate",
      generation_parameters: { temperature: 0.2 },
      created_at: "2026-07-13T11:00:00Z",
    };
    fetchMock
      .mockReset()
      .mockResolvedValueOnce(jsonResponse([createdVersion]))
      .mockResolvedValueOnce(jsonResponse(candidateVersion, 201));

    render(<App />);
    expect(await screen.findByText(createdVersion.name)).toBeInTheDocument();

    await user.type(screen.getByLabelText("Version name"), candidateVersion.name);
    await user.type(screen.getByLabelText("Model provider"), candidateVersion.model_provider);
    await user.type(screen.getByLabelText("Model name"), candidateVersion.model_name);
    await user.type(screen.getByLabelText("System prompt"), candidateVersion.system_prompt);
    await user.clear(screen.getByLabelText("Generation parameters (JSON)"));
    await user.click(screen.getByLabelText("Generation parameters (JSON)"));
    await user.paste(JSON.stringify(candidateVersion.generation_parameters));
    await user.click(screen.getByRole("button", { name: "Create version" }));

    expect(await screen.findByText(candidateVersion.name)).toBeInTheDocument();
    expect(screen.getByText(createdVersion.name)).toBeInTheDocument();
    expect(screen.getByText("2 total")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "POST" });
  });
});
