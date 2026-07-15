import { spawn } from "node:child_process";
import { createServer } from "node:net";
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
  { allowFailure = false, stdio = "inherit", timeoutMs = 60_000 } = {},
) {
  return new Promise((resolve, reject) => {
    const output = [];
    let settled = false;
    const child = spawn(command, args, {
      cwd: frontendRoot,
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

function runPlaywright(args, options) {
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
    options,
  );
}

await assertPortAvailable();
const server = spawn(
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

try {
  console.log("Waiting for the Vite acceptance server...");
  await waitForServer();
  console.log(`Opening ${browser} through Playwright CLI...`);
  await runPlaywright(["open", "about:blank", "--browser", browser]);
  console.log("Running mobile and desktop viewport assertions...");
  const assertionResult = await runPlaywright(
    [
      "--json",
      "run-code",
      "--filename",
      path.join(frontendRoot, "e2e", "mobile-evaluation-runs.js"),
    ],
    { stdio: "pipe" },
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
  console.log(`Mobile Evaluation Runs browser regression passed in ${browser}.`);
} finally {
  try {
    await runPlaywright(["close"], { allowFailure: true, timeoutMs: 20_000 });
  } finally {
    await stopServer(server);
  }
}
