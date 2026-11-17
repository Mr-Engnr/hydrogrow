#!/usr/bin/env node
/**
 * Local Edition dashboard build.
 *
 * Only the files that differ from the cloud dashboard live in local-edition/dashboard/src
 * (data-source badge, sensor-offline handling, relative API base). Every other page, style
 * and image comes from the repo's dashboard/ folder, so each shared file exists once.
 *
 *   cd local-edition/dashboard
 *   npm ci
 *   npm run build      # -> local-edition/backend/build, served by the Express backend
 *   npm start          # dev server on :3000, proxies /api to the backend on :8080
 *
 * Steps: copy ../../dashboard/{public,src} into .stage/, copy ./src on top, then run
 * react-scripts inside .stage/. Modules resolve from local-edition/dashboard/node_modules.
 * Cross-platform (Windows, macOS, Raspberry Pi OS); no symlinks.
 */
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const mode = process.argv[2] || "build";
if (!["build", "start"].includes(mode)) {
  console.error(`usage: node scripts/build.js [build|start]  (got ${mode})`);
  process.exit(2);
}

const here = path.resolve(__dirname, "..");                 // local-edition/dashboard
const shared = path.resolve(here, "..", "..", "dashboard"); // repo dashboard (cloud edition)
const stage = path.join(here, ".stage");
const buildPath = path.resolve(here, "..", "backend", "build");

for (const d of ["src", "public"]) {
  if (!fs.existsSync(path.join(shared, d))) {
    console.error(`missing ${path.join(shared, d)}; run this from a full checkout of the repo`);
    process.exit(1);
  }
}

fs.rmSync(stage, { recursive: true, force: true });
fs.mkdirSync(stage, { recursive: true });
fs.cpSync(path.join(shared, "public"), path.join(stage, "public"), { recursive: true });
fs.cpSync(path.join(shared, "src"), path.join(stage, "src"), { recursive: true });

// Local Edition overrides, listed so the build log shows exactly what differs.
const overrides = [];
(function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else overrides.push(path.relative(path.join(here, "src"), p));
  }
})(path.join(here, "src"));
fs.cpSync(path.join(here, "src"), path.join(stage, "src"), { recursive: true, force: true });
fs.copyFileSync(path.join(here, "package.json"), path.join(stage, "package.json"));
console.log(`staged shared dashboard + ${overrides.length} Local Edition file(s):\n  ` + overrides.join("\n  "));

const env = {
  ...process.env,
  BUILD_PATH: buildPath,
  GENERATE_SOURCEMAP: process.env.GENERATE_SOURCEMAP || "false", // smaller build on the Pi
  CI: "",                       // CRA treats warnings as errors when CI=true
  BROWSER: process.env.BROWSER || "none",
};
const bin = path.join(here, "node_modules", "react-scripts", "bin", "react-scripts.js");
if (!fs.existsSync(bin)) {
  console.error("react-scripts not installed; run npm ci in local-edition/dashboard first");
  process.exit(1);
}
const r = spawnSync(process.execPath, [bin, mode], { stdio: "inherit", env, cwd: stage });
if (r.status !== 0) process.exit(r.status || 1);
if (mode === "build") console.log(`\nDashboard built into ${buildPath}`);
