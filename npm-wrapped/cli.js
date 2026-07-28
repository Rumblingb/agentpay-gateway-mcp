#!/usr/bin/env node

/**
 * AgentPay Gateway MCP — npm wrapper
 * Auto-installs Python dependencies and runs the Python MCP server.
 */

const { execSync, spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const SERVER_DIR = path.resolve(__dirname, "..");
const SERVER_SCRIPT = path.join(SERVER_DIR, "server.py");
const REQUIREMENTS_FILE = path.join(SERVER_DIR, "requirements.txt");

const PIP_PACKAGES = [
  "mcp>=1.0.0",
  "httpx>=0.25.0",
  "supabase>=2.0.0",
  "stripe>=8.0.0",
  "python-dotenv>=1.0.0",
  "anyio>=4.0.0",
];

function log(msg) {
  process.stderr.write(`[gateway-mcp] ${msg}\n`);
}

function runSync(cmd, opts = {}) {
  return execSync(cmd, {
    stdio: ["inherit", "pipe", "pipe"],
    ...opts,
  });
}

function installDeps() {
  log("Checking Python dependencies...");

  try {
    runSync("python3 -c 'import mcp'", { stdio: ["inherit", "pipe", "pipe"] });
    log("All dependencies already installed.");
    return;
  } catch {
    log("Installing requirements...");
  }

  // Try pip install from requirements.txt first
  if (fs.existsSync(REQUIREMENTS_FILE)) {
    try {
      runSync(`pip install -r "${REQUIREMENTS_FILE}"`, {
        stdio: ["inherit", "pipe", "pipe"],
      });
      log("Dependencies installed via requirements.txt.");
      return;
    } catch (e) {
      log(`pip install from requirements.txt failed: ${e.message}`);
    }
  }

  // Fall back to individual packages
  const installCmd = `pip install ${PIP_PACKAGES.join(" ")}`;
  try {
    runSync(installCmd, { stdio: ["inherit", "pipe", "pipe"] });
    log("Dependencies installed.");
  } catch (e) {
    log(`Failed to install dependencies: ${e.message}`);
    log("Try running: pip install mcp httpx supabase stripe python-dotenv anyio");
    process.exit(1);
  }
}

function runServer() {
  if (!fs.existsSync(SERVER_SCRIPT)) {
    log(`ERROR: server.py not found at ${SERVER_SCRIPT}`);
    process.exit(1);
  }

  log(`Starting server: python3 ${SERVER_SCRIPT}`);
  const child = spawn(
    "python3",
    [SERVER_SCRIPT],
    {
      cwd: SERVER_DIR,
      stdio: ["inherit", "inherit", "inherit"],
      env: { ...process.env },
    }
  );

  child.on("error", (err) => {
    log(`Failed to start Python server: ${err.message}`);
    process.exit(1);
  });

  child.on("exit", (code) => {
    process.exit(code || 0);
  });
}

// Main
installDeps();
runServer();
