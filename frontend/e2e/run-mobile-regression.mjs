import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";
const nodeBin = path.dirname(process.execPath);
const npxInvocation = isWindows
  ? {
      command: process.execPath,
      prefix: [path.join(nodeBin, "node_modules", "npm", "bin", "npx-cli.js")],
    }
  : { command: "npx", prefix: [] };
const browser = process.env.PLAYWRIGHT_BROWSER ?? (process.env.CI ? "chrome" : "msedge");
const session = `mobile-regression-${process.pid}`;
const serverOutput = [];
const repositoryPlaywrightState = path.join(frontendRoot, ".playwright-cli");
const browserProgramTemplate = path.join(frontendRoot, "e2e", "mobile-evaluation-runs.js");
const browserArtifactDirectory = path.resolve(frontendRoot, "..", "output", "playwright");
const browserArtifactPlaceholder = '"__LLM_EVAL_LAB_PLAYWRIGHT_OUTPUT_DIR__"';
const browserArtifacts = ["demo-human-review.png", "demo-release-decision.png"].map(
  (fileName) => path.join(browserArtifactDirectory, fileName),
);
const trackedDocumentationScreenshots = [
  "demo-human-review.png",
  "demo-release-decision.png",
].map((fileName) => path.resolve(frontendRoot, "..", "docs", "screenshots", fileName));

async function captureFileHashes(filePaths) {
  return new Map(
    await Promise.all(
      filePaths.map(async (filePath) => [
        filePath,
        createHash("sha256").update(await readFile(filePath)).digest("hex"),
      ]),
    ),
  );
}

async function assertFilesUnchanged(originalHashes) {
  const currentHashes = await captureFileHashes([...originalHashes.keys()]);
  const changedFiles = [...originalHashes.entries()]
    .filter(([filePath, originalHash]) => currentHashes.get(filePath) !== originalHash)
    .map(([filePath]) => path.relative(frontendRoot, filePath).replaceAll("\\", "/"));
  if (changedFiles.length > 0) {
    throw new Error(
      `Browser regression changed tracked documentation screenshots: ${changedFiles.join(", ")}`,
    );
  }
}

async function captureDirectoryFileHashes(directory, relativeDirectory = "") {
  const currentDirectory = path.join(directory, relativeDirectory);
  let entries;
  try {
    entries = await readdir(currentDirectory, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") return new Map();
    throw error;
  }
  const entryHashes = await Promise.all(
    entries.map(async (entry) => {
      const relativePath = path.join(relativeDirectory, entry.name);
      if (entry.isDirectory()) {
        return captureDirectoryFileHashes(directory, relativePath);
      }
      const filePath = path.join(directory, relativePath);
      return new Map([
        [relativePath, createHash("sha256").update(await readFile(filePath)).digest("hex")],
      ]);
    }),
  );
  return new Map(entryHashes.flatMap((hashes) => [...hashes.entries()]));
}

async function assertDirectoryFilesUnchanged(originalHashes, directory) {
  const currentHashes = await captureDirectoryFileHashes(directory);
  const allPaths = new Set([...originalHashes.keys(), ...currentHashes.keys()]);
  const changedFiles = [...allPaths].filter(
    (relativePath) => originalHashes.get(relativePath) !== currentHashes.get(relativePath),
  );
  if (changedFiles.length > 0) {
    throw new Error(
      `Browser regression changed repository Playwright state: ${changedFiles.join(", ")}`,
    );
  }
}

async function captureFileModificationTimes(filePaths) {
  return new Map(
    await Promise.all(
      filePaths.map(async (filePath) => {
        try {
          return [filePath, (await stat(filePath, { bigint: true })).mtimeNs];
        } catch (error) {
          if (error.code === "ENOENT") return [filePath, null];
          throw error;
        }
      }),
    ),
  );
}

async function assertFilesRefreshed(originalModificationTimes) {
  const currentModificationTimes = await captureFileModificationTimes(
    [...originalModificationTimes.keys()],
  );
  const staleFiles = [...originalModificationTimes.entries()]
    .filter(
      ([filePath, originalTime]) =>
        currentModificationTimes.get(filePath) === null ||
        currentModificationTimes.get(filePath) === originalTime,
    )
    .map(([filePath]) => path.relative(frontendRoot, filePath).replaceAll("\\", "/"));
  if (staleFiles.length > 0) {
    throw new Error(`Browser regression did not refresh runtime artifacts: ${staleFiles.join(", ")}`);
  }
}

async function writeConfiguredBrowserProgram(workspace) {
  const template = await readFile(browserProgramTemplate, "utf8");
  if (
    !template.includes(browserArtifactPlaceholder) ||
    template.indexOf(browserArtifactPlaceholder) !== template.lastIndexOf(browserArtifactPlaceholder)
  ) {
    throw new Error("Browser program must contain exactly one artifact-directory placeholder.");
  }
  const configuredProgram = template.replace(
    browserArtifactPlaceholder,
    JSON.stringify(browserArtifactDirectory),
  );
  const configuredProgramPath = path.join(workspace, "mobile-evaluation-runs.js");
  await writeFile(configuredProgramPath, configuredProgram, "utf8");
  return configuredProgramPath;
}

function terminateProcessTree(child) {
  return new Promise((resolve) => {
    if (child.pid === undefined) {
      resolve();
      return;
    }
    if (!isWindows) {
      try {
        process.kill(-child.pid, "SIGTERM");
      } catch (error) {
        if (error.code !== "ESRCH") child.kill("SIGTERM");
      }
      resolve();
      return;
    }
    const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
      stdio: "ignore",
      windowsHide: true,
    });
    killer.on("error", () => {
      child.kill("SIGTERM");
      resolve();
    });
    killer.on("exit", () => resolve());
  });
}

function run(
  command,
  args,
  { allowFailure = false, cwd = frontendRoot, stdio = "inherit", timeoutMs = 60_000 } = {},
) {
  return new Promise((resolve, reject) => {
    const output = [];
    let settled = false;
    const child = spawn(command, args, {
      cwd,
      detached: !isWindows,
      stdio,
      windowsHide: true,
    });
    if (stdio === "pipe") {
      child.stdout.on("data", (chunk) => output.push(chunk.toString()));
      child.stderr.on("data", (chunk) => output.push(chunk.toString()));
    }
    const timeout = setTimeout(async () => {
      if (settled) return;
      settled = true;
      await terminateProcessTree(child);
      reject(
        new Error(`${command} ${args.join(" ")} timed out after ${timeoutMs}ms.`),
      );
    }, timeoutMs);
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      reject(error);
    });
    child.on("exit", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (code === 0 || allowFailure) resolve({ code, output: output.join("") });
      else {
        reject(
          new Error(
            `${command} ${args.join(" ")} exited with code ${code}.\n${output.join("")}`,
          ),
        );
      }
    });
  });
}

function assertPortAvailable() {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.unref();
    probe.once("error", () => {
      reject(new Error("Port 5173 is already in use; browser regression did not start."));
    });
    probe.listen({ host: "127.0.0.1", port: 5173, exclusive: true }, () => {
      probe.close(resolve);
    });
  });
}

async function waitForServer() {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`Vite exited before becoming ready.\n${serverOutput.join("")}`);
    }
    try {
      const response = await fetch("http://127.0.0.1:5173");
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Vite did not start within 30 seconds.\n${serverOutput.join("")}`);
}

async function stopServer(server) {
  await terminateProcessTree(server);
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline) {
    try {
      await fetch("http://127.0.0.1:5173");
      await new Promise((resolve) => setTimeout(resolve, 100));
    } catch {
      return;
    }
  }
  throw new Error("Vite still owns port 5173 after browser regression cleanup.");
}

function runPlaywright(args, options = {}) {
  return run(
    npxInvocation.command,
    [
      ...npxInvocation.prefix,
      "--yes",
      "--package",
      "@playwright/cli@0.1.17",
      "playwright-cli",
      `-s=${session}`,
      ...args,
    ],
    { ...options, cwd: playwrightWorkspace },
  );
}

const originalDocumentationScreenshotHashes = await captureFileHashes(
  trackedDocumentationScreenshots,
);
const originalRepositoryPlaywrightHashes = await captureDirectoryFileHashes(
  repositoryPlaywrightState,
);
const originalBrowserArtifactModificationTimes = await captureFileModificationTimes(
  browserArtifacts,
);
const playwrightWorkspace = await mkdtemp(path.join(tmpdir(), "llm-eval-lab-playwright-"));
let playwrightStarted = false;
let server;

try {
  await assertPortAvailable();
  const configuredBrowserProgram = await writeConfiguredBrowserProgram(playwrightWorkspace);
  server = spawn(
    process.execPath,
    [
      path.join(frontendRoot, "node_modules", "vite", "bin", "vite.js"),
      "--host",
      "127.0.0.1",
      "--port",
      "5173",
      "--strictPort",
    ],
    {
      cwd: frontendRoot,
      detached: !isWindows,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    },
  );
  server.stdout.on("data", (chunk) => serverOutput.push(chunk.toString()));
  server.stderr.on("data", (chunk) => serverOutput.push(chunk.toString()));
  console.log("Waiting for the Vite acceptance server...");
  await waitForServer();
  console.log(`Opening ${browser} through Playwright CLI...`);
  playwrightStarted = true;
  await runPlaywright(["open", "about:blank", "--browser", browser]);
  console.log("Running mobile and desktop viewport assertions...");
  const assertionResult = await runPlaywright(
    [
      "--json",
      "run-code",
      "--filename",
      configuredBrowserProgram,
    ],
    { stdio: "pipe", timeoutMs: 120_000 },
  );
  let assertionPayload;
  try {
    assertionPayload = JSON.parse(assertionResult.output.trim());
  } catch {
    throw new Error(`Playwright CLI returned invalid JSON:\n${assertionResult.output}`);
  }
  if (assertionPayload.isError) {
    throw new Error(`Playwright browser assertion failed: ${assertionPayload.error}`);
  }
  await assertFilesRefreshed(originalBrowserArtifactModificationTimes);
  await assertFilesUnchanged(originalDocumentationScreenshotHashes);
  console.log(`Mobile Evaluation Runs browser regression passed in ${browser}.`);
} finally {
  try {
    if (playwrightStarted) {
      try {
        await runPlaywright(["close"], { allowFailure: true, timeoutMs: 20_000 });
      } catch (error) {
        console.warn(`Playwright cleanup warning: ${error.message}`);
      }
    }
  } finally {
    try {
      if (server) await stopServer(server);
    } finally {
      await rm(playwrightWorkspace, { recursive: true, force: true });
    }
  }
}
await assertDirectoryFilesUnchanged(originalRepositoryPlaywrightHashes, repositoryPlaywrightState);
