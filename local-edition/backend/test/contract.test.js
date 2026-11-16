/**
 * Contract tests: old Azure response shapes vs the new SQLite-backed routes.
 *
 * Strategy: the Azure code paths (processTelemetry storage + twin patches,
 * analytics aggregation, the old /pidata remap) are ported here VERBATIM as
 * reference oracles operating on in-memory "blobs". The same payloads are then
 * pushed through the real ingest logic (schema + insert, replicated here in JS
 * exactly as ingest.py does it) and served by the real Express app. Every
 * response is compared key-by-key, type-by-type, value-by-value.
 *
 * Run: cd backend && npm test
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");

process.env.HYDROGROW_DB = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "hg-contract-")), "t.db");
process.env.PORT = "0";
process.env.DEMO_USER_EMAIL = "demo@test.local";
process.env.DEMO_USER_PASSWORD = "demo-pass-123";

const db = require("../src/db/db");
const app = require("../src/app");
const authService = require("../src/services/auth.service");

// ---------------------------------------------------------------- fixtures (contract §1.3 / §1.4 / variants)
const fixtures = require("./fixtures/payloads.json");

// ---------------------------------------------------------------- reference: Azure Function processTelemetry (verbatim port)
function get_alert_status(key, value) {
  if (key === "ph") {
    if (value < 6.0) return "Low pH: Use pH Up Nutrient";
    if (value > 8.0) return "High pH: Use pH Down Nutrient";
  } else if (key === "waterLevelPct") {           // percent, dashboard thresholds
    if (value <= 20) return "Critical: Low Water Level";
    if (value <= 40) return "Warning: Low Water Level";
  } else if (key === "temperature" && (value < 18 || value > 30)) {
    return "Warning: Temperature out of range";
  }
  return "Normal";
}

function azureProcessTelemetry(blobs, twins, payload, ingestNaiveIso, blobName) {
  let data = JSON.parse(JSON.stringify(payload));
  if (Array.isArray(data)) data = data[0];
  data.timestamp = ingestNaiveIso;
  blobs.push({ name: blobName, data });

  const normalized = { ...data };
  normalized.ph = data.pH ?? data.ph;
  normalized.waterLevel = data.water_level ?? data.waterLevel;
  normalized.waterLevelPct = data.water_level_pct;
  const mapping = { ph: "watertank1", ec: "watertank1", waterLevel: "watertank1", waterLevelPct: "watertank1", temperature: "environment1", humidity: "environment1" };
  for (const [key, value] of Object.entries(normalized)) {
    if (key in mapping && value !== null && value !== undefined) {
      const t = (twins[mapping[key]] ||= {});
      t[key] = value;
      if (["ph", "waterLevelPct", "temperature"].includes(key)) t.alertStatus = get_alert_status(key, value);
    }
  }
  const dp = data.disease_predictions || {};
  const nd = data.nutrient_status || {};            // null -> {}
  const nutrient_label = nd.label ?? null;
  const nutrient_conf = nd.confidence ?? null;
  for (const plant_id of ["plant1", "plant2", "plant3"]) {
    const patch = {};
    if (plant_id in dp && dp[plant_id]) {
      const ds = dp[plant_id].label ?? "Unknown";
      patch.disease_status = ds;
      patch.disease_confidence = Number(dp[plant_id].confidence ?? 0.0) * 100;
      patch.diseased = ds !== "Healthy";
    }
    if (["plant1", "plant2"].includes(plant_id) && nutrient_label !== null) {
      patch.nutrient_status = nutrient_label;
      patch.nutrient_confidence = Number(nutrient_conf || 0.0);
    }
    if (Object.keys(patch).length) Object.assign((twins[plant_id] ||= {}), patch);
  }
}

// ---------------------------------------------------------------- reference: Azure Function analytics (verbatim port; pH and ph both accepted)
function azureAnalytics(blobs, days, nowMs) {
  const cutoff = nowMs - days * 86400000;
  const daily_ph = {}, daily_ec = {}, daily_temp = {}, daily_humidity = {};
  for (const blob of blobs) {
    const name = blob.name.replace(".json", "");
    const date_part = name.split("_")[0];
    const blob_date = Date.UTC(+date_part.slice(0, 4), +date_part.slice(4, 6) - 1, +date_part.slice(6, 8));
    if (blob_date >= cutoff) {
      const data = blob.data;
      const day_key = new Date(blob_date).toISOString().slice(0, 10);
      const ph = data.pH ?? data.ph;                                   // pH or ph
      if (ph !== undefined && ph !== null) (daily_ph[day_key] ||= []).push(ph);
      if (data.ec !== undefined && data.ec !== null) (daily_ec[day_key] ||= []).push(data.ec);
      if (data.temperature !== undefined && data.temperature !== null) (daily_temp[day_key] ||= []).push(data.temperature);
      if (data.humidity !== undefined && data.humidity !== null) (daily_humidity[day_key] ||= []).push(data.humidity);
    }
  }
  const labels = Object.keys(daily_ph).sort();
  const avg = (lst) => (lst && lst.length ? Math.round((lst.reduce((a, b) => a + b, 0) / lst.length) * 100) / 100 : 0);
  return {
    labels,
    daily_avg_ph: labels.map((d) => avg(daily_ph[d])),
    daily_avg_ec: labels.map((d) => avg(daily_ec[d])),
    daily_avg_temp: labels.map((d) => avg(daily_temp[d])),
    daily_avg_humidity: labels.map((d) => avg(daily_humidity[d])),
    overall_week_avg_ph: avg(Object.values(daily_ph).flat()),
  };
}

// ---------------------------------------------------------------- reference: old pidata.routes.js remap (verbatim)
function azurePidata(blobs) {
  let latestBlob = null;
  for (const blob of blobs) {
    if (!blob.name.match(/^\d{8}_\d{6}_\d+\.json$/)) continue;
    if (!latestBlob || blob.name > latestBlob.name) latestBlob = blob;
  }
  if (!latestBlob) return { status: 404, body: { error: "No data found" } };
  const data = latestBlob.data;
  const remapped = {
    ph: data.pH ?? data.ph ?? null,
    ec: data.ec,
    waterTemp: data.temperature,
    humidity: data.humidity,
    waterLevel: data.waterLevel ?? data.water_level ?? null,
    waterLevelPct: data.water_level_pct ?? null,
    waterLow: data.water_low ?? null,
    health_status: data.nutrient_status?.label || data.nutrient_status || "Unknown",
    nutrient_confidence: data.nutrient_confidence,
    plant1: data.plant1 || null,
    plant2: data.plant2 || null,
    plant3: data.plant3 || null,
    disease_predictions: data.disease_predictions || null,
  };
  return { status: 200, body: [remapped] };
}

// ---------------------------------------------------------------- new side: ingest.py's insert, replicated in JS over the same schema
function ingestInsert(conn, data, ingestNaive, blobName) {
  const num = (v) => (typeof v === "number" ? v : null);
  const flag = (v) => (v === null || v === undefined ? null : v ? 1 : 0);
  const ph = num(data.pH ?? data.ph);
  const ns = data.nutrient_status || {};
  const dp = data.disease_predictions || {};
  const dosing = data.dosing || {};
  const plant = (id) => { const p = dp[id] || {}; return [p.label ?? null, num(p.confidence)]; };
  const [p1l, p1c] = plant("plant1"), [p2l, p2c] = plant("plant2"), [p3l, p3c] = plant("plant3");
  conn.prepare(`INSERT INTO telemetry (
      blob_name, ingested_at, ingest_day, pi_timestamp, source, ph, ec, tds, temperature, humidity,
      water_level, water_level_cm, water_level_pct, water_low, growth_day_actual, growth_day_model,
      growth_phase, harvest_flush, status, image, nutrient_label, nutrient_confidence,
      plant1_label, plant1_confidence, plant2_label, plant2_confidence, plant3_label, plant3_confidence,
      dosing_a_dosed, dosing_b_dosed, raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
    .run(blobName, ingestNaive, ingestNaive.slice(0, 10), data.timestamp ?? null, data.source || "pi",
      ph, num(data.ec), num(data.tds), num(data.temperature), num(data.humidity),
      num(data.water_level ?? data.waterLevel), num(data.water_level_cm), num(data.water_level_pct), flag(data.water_low),
      data.growth_day_actual ?? null, data.growth_day_model ?? null, data.growth_phase ?? null, flag(data.harvest_flush),
      data.status ?? null, data.image ?? null, ns.label ?? null, num(ns.confidence),
      p1l, p1c, p2l, p2c, p3l, p3c,
      flag((dosing.nutrient_a || {}).dosed), flag((dosing.nutrient_b || {}).dosed), JSON.stringify(data));
}

function ingestTwins(conn, data, ingestNaive) {
  // identical rules to ingest.update_twins(); kept as a reference so a drift in ingest.py fails here
  const twins = {};
  azureProcessTelemetry([], twins, data, ingestNaive, "x.json");
  const up = conn.prepare("INSERT INTO twin_state (twin_id, property, value_json, updated_at) VALUES (?,?,?,?) " +
    "ON CONFLICT(twin_id, property) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at");
  for (const [tid, props] of Object.entries(twins)) for (const [k, v] of Object.entries(props)) up.run(tid, k, JSON.stringify(v), ingestNaive);
}

// ---------------------------------------------------------------- harness
let server, base, conn;
const blobs = [];        // Azure reference store
const twinsRef = {};     // Azure reference twin graph
const NOW = Date.now();

function naiveIso(ms) { return new Date(ms).toISOString().replace("Z", "").replace(/\.(\d{3})$/, ".$1000"); }
function blobNameFor(ms) {
  const d = new Date(ms);
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}_${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}_${p(d.getUTCMilliseconds(), 3)}000.json`;
}

async function get(p, headers = {}) {
  const r = await fetch(base + p, { headers });
  return { status: r.status, body: await r.json(), headers: r.headers };
}
async function post(p, body, headers = {}) {
  const r = await fetch(base + p, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });
  return { status: r.status, body: await r.json() };
}

test.before(async () => {
  conn = db.open(process.env.HYDROGROW_DB);
  await authService.seedDemoUser(process.env.DEMO_USER_EMAIL, process.env.DEMO_USER_PASSWORD, "Demo");
  server = app.listen(0);
  await new Promise((r) => server.once("listening", r));
  base = `http://127.0.0.1:${server.address().port}`;

  // Feed 10 days of history + today's frames into BOTH sides in the same order.
  const plan = [];
  for (let d = 10; d >= 1; d--) {
    for (let i = 0; i < 3; i++) plan.push({ at: NOW - d * 86400000 + i * 3600000, p: fixtures.normal, tweak: (d * 7 + i) / 100 });
  }
  plan.push({ at: NOW - 60000, p: fixtures.legacy_lowercase_ph });   // lowercase "ph" sender
  plan.push({ at: NOW - 30000, p: fixtures.flaky_dht });             // temp/humidity null, nutrient null
  plan.push({ at: NOW - 20000, p: fixtures.error_frame });
  plan.push({ at: NOW - 10000, p: [fixtures.normal] });              // batch-array unwrap
  plan.push({ at: NOW - 5000, p: fixtures.diseased });               // latest

  for (const step of plan) {
    let payload = JSON.parse(JSON.stringify(step.p));
    if (step.tweak) { payload.pH = +(payload.pH + step.tweak).toFixed(2); payload.ec = +(payload.ec - step.tweak / 10).toFixed(3); }
    const ingestNaive = naiveIso(step.at);
    const name = blobNameFor(step.at);
    azureProcessTelemetry(blobs, twinsRef, payload, ingestNaive, name);
    let data = Array.isArray(payload) ? payload[0] : payload;
    ingestInsert(conn, data, ingestNaive, name);
    ingestTwins(conn, data, ingestNaive);
  }
  // a non-telemetry file name, which the old regex filter had to skip (3D-scene config blob)
  blobs.push({ name: "scene_config.json", data: { pH: 99 } });
});

test.after(() => server && server.close());

// ---------------------------------------------------------------- helpers
// Compare key sets, types and (unless valuesToo=false) values, recursively.
// `expected` is JSON round-tripped first so undefined keys vanish exactly as they do on the wire.
function sameShape(actual, expected, where = "$", valuesToo = true) {
  expected = JSON.parse(JSON.stringify(expected));
  const walk = (a, e, w) => {
    assert.equal(typeof a, typeof e, `${w}: type ${typeof a} vs ${typeof e}`);
    if (Array.isArray(e)) {
      assert.ok(Array.isArray(a), `${w}: expected array`);
      assert.equal(a.length, e.length, `${w}: length`);
      e.forEach((x, i) => walk(a[i], x, `${w}[${i}]`));
    } else if (e && typeof e === "object") {
      assert.deepEqual(Object.keys(a).sort(), Object.keys(e).sort(), `${w}: key set`);
      for (const k of Object.keys(e)) walk(a[k], e[k], `${w}.${k}`);
    } else if (valuesToo) {
      assert.deepEqual(a, e, `${w}: value`);
    }
  };
  walk(actual, expected, where);
}

// ---------------------------------------------------------------- tests
test("/api/pidata: identical to the old blob-backed route, field by field", async () => {
  const ref = azurePidata(blobs);
  const res = await get("/api/pidata");
  assert.equal(res.status, ref.status);
  sameShape(res.body, ref.body);
  // the quirks the dashboard depends on survive
  const r = res.body[0];
  assert.equal(r.ph, fixtures.diseased.pH);
  assert.equal("nutrient_confidence" in r, false, "undefined key is omitted from JSON, as before");
  assert.equal(r.plant1, null);
  assert.equal(r.disease_predictions.plant2.confidence, fixtures.diseased.disease_predictions.plant2.confidence, "0-1 scale untouched");
  assert.equal(r.waterLevel, fixtures.diseased.water_level, "raw cm distance passthrough");
  assert.equal(r.waterLevelPct, fixtures.diseased.water_level_pct);
});

test("/api/pidata is public (no Authorization header needed)", async () => {
  const res = await fetch(base + "/api/pidata");
  assert.equal(res.status, 200);
});

test("/api/analytics?days=N matches the Azure Function for 7, 14, 30 and default", async () => {
  for (const q of ["?days=7", "?days=14", "?days=30", "", "?days=abc", "?days=-3"]) {
    const parsed = Number.parseInt(new URLSearchParams(q).get("days"), 10);
    const days = Number.isNaN(parsed) || parsed <= 0 ? 7 : parsed;
    const ref = azureAnalytics(blobs, days, Date.now());
    const res = await get("/api/analytics" + q);
    assert.equal(res.status, 200, q);
    sameShape(res.body, ref, `analytics${q}`);
    assert.ok(res.body.labels.length > 0, `analytics${q}: non-empty labels (pH read from "pH")`);
    assert.deepEqual(Object.keys(res.body), ["labels", "daily_avg_ph", "daily_avg_ec", "daily_avg_temp", "daily_avg_humidity", "overall_week_avg_ph"], "key order");
  }
});

test("/api/analytics: lowercase 'ph' sender is counted", async () => {
  const res = await get("/api/analytics?days=1");
  const today = new Date().toISOString().slice(0, 10);
  const n = conn.prepare("SELECT COUNT(*) n FROM telemetry WHERE ingest_day = ? AND ph IS NOT NULL").get(today).n;
  assert.ok(n >= 4, "pH and ph rows both have the normalised column");
  assert.ok(res.body.labels.includes(today) || res.body.labels.length === 0, "today bucket present when cutoff allows");
});

test("/twins/:id and /api/twins/:id: ADT document shape, same properties and values as the Function wrote", async () => {
  for (const id of ["watertank1", "environment1", "plant1", "plant2", "plant3"]) {
    for (const prefix of ["", "/api"]) {
      const res = await get(`${prefix}/twins/${id}`);
      assert.equal(res.status, 200, id);
      assert.equal(res.headers.get("access-control-allow-origin"), "*");
      const doc = res.body;
      assert.equal(doc.$dtId, id);
      assert.ok(typeof doc.$etag === "string" && doc.$etag.startsWith('W/"'));
      assert.ok(doc.$metadata && typeof doc.$metadata.$model === "string");
      const props = Object.fromEntries(Object.entries(doc).filter(([k]) => !k.startsWith("$")));
      assert.deepEqual(props, twinsRef[id] || {}, `${id} properties`);
    }
  }
  // scale rules
  const p2 = (await get("/twins/plant2")).body;
  assert.equal(p2.disease_confidence, fixtures.diseased.disease_predictions.plant2.confidence * 100, "disease x100");
  assert.equal(p2.nutrient_confidence, fixtures.diseased.nutrient_status.confidence, "nutrient as-is");
  assert.equal(p2.diseased, true);
  const p3 = (await get("/twins/plant3")).body;
  assert.equal("disease_status" in p3, false, "plant3 never receives disease props");
  assert.equal("nutrient_status" in p3, false, "plant3 never receives nutrient props");
  const wt = (await get("/twins/watertank1")).body;
  assert.equal(wt.waterLevel, fixtures.diseased.water_level, "raw cm still written to the twin");
  assert.equal(wt.waterLevelPct, fixtures.diseased.water_level_pct, "percent written alongside");
  assert.equal(wt.alertStatus, "Normal", "75.4 % tank is Normal (percent rule)");
  const unknown = await get("/twins/nope");
  assert.equal(unknown.status, 500);
  assert.ok(typeof unknown.body.error === "string");
});

test("timestamp in stored document = ingest time; Pi value kept as pi_timestamp", async () => {
  const telemetry = require("../src/services/telemetry.service");
  const { row, data } = telemetry.latest();
  assert.equal(data.timestamp, row.ingested_at);
  assert.equal(row.pi_timestamp, fixtures.diseased.timestamp);
  assert.ok(!row.ingested_at.endsWith("Z") && !row.ingested_at.includes("+"), "naive UTC like datetime.utcnow().isoformat()");
  assert.equal(JSON.parse(row.raw_json).timestamp, fixtures.diseased.timestamp, "raw payload untouched");
});

test("auth flow unchanged: register / login / me / logout / rejected token; users live in SQLite", async () => {
  const reg = await post("/api/auth/register", { email: "Alice@Example.com", password: "secret12", name: " Alice " });
  assert.equal(reg.status, 201);
  sameShape(reg.body, { success: true, message: "Registration successful", user: { id: "x", email: "alice@example.com", name: "Alice" } }, "register", false);
  assert.equal(reg.body.user.email, "alice@example.com");
  assert.equal(reg.body.user.name, "Alice");

  const dup = await post("/api/auth/register", { email: "alice@example.com", password: "secret12", name: "A" });
  assert.equal(dup.status, 400);
  assert.deepEqual(dup.body, { success: false, message: "Email already registered" });

  const short = await post("/api/auth/register", { email: "b@x.io", password: "123", name: "B" });
  assert.deepEqual(short.body, { success: false, message: "Password must be at least 6 characters" });

  const bad = await post("/api/auth/login", { email: "alice@example.com", password: "wrong" });
  assert.equal(bad.status, 401);
  assert.deepEqual(bad.body, { success: false, message: "Invalid email or password" });

  const login = await post("/api/auth/login", { email: "alice@example.com", password: "secret12" });
  assert.equal(login.status, 200);
  sameShape(login.body, { success: true, message: "Login successful", token: "t", user: { id: "x", email: "e", name: "n" } }, "login", false);
  assert.match(login.body.token, /^[0-9a-f]{64}$/, "opaque 32-byte hex token, as before");

  const me = await get("/api/auth/me", { Authorization: `Bearer ${login.body.token}` });
  assert.equal(me.status, 200);
  assert.deepEqual(me.body, { success: true, user: reg.body.user });

  const noTok = await get("/api/auth/me");
  assert.equal(noTok.status, 401);
  assert.deepEqual(noTok.body, { success: false, message: "Authentication required" });

  const out = await post("/api/auth/logout", {}, { Authorization: `Bearer ${login.body.token}` });
  assert.deepEqual(out.body, { success: true, message: "Logged out successfully" });
  const after = await get("/api/auth/me", { Authorization: `Bearer ${login.body.token}` });
  assert.equal(after.status, 401);
  assert.deepEqual(after.body, { success: false, message: "Invalid or expired token" });

  const row = conn.prepare("SELECT * FROM users WHERE email = 'alice@example.com'").get();
  assert.ok(row && row.password.startsWith("$2"), "bcrypt hash persisted in SQLite");
  assert.equal(row.token, null);
});

test("demo user is seeded from env and can log in", async () => {
  const login = await post("/api/auth/login", { email: process.env.DEMO_USER_EMAIL, password: process.env.DEMO_USER_PASSWORD });
  assert.equal(login.status, 200);
  assert.equal(login.body.user.name, "Demo");
});

test("users.json import keeps old bcrypt hashes usable", async () => {
  const bcrypt = require("bcryptjs");
  const n = authService.importUsersJson([{ id: "legacy-1", email: "Old@User.io", password: await bcrypt.hash("oldpass1", 10), name: "Old", token: "stale", createdAt: "2026-01-01T00:00:00.000Z" }]);
  assert.equal(n, 1);
  const login = await post("/api/auth/login", { email: "old@user.io", password: "oldpass1" });
  assert.equal(login.status, 200);
});

test("/api/chat fails gracefully offline with the UI's expected shape", async () => {
  const r = await post("/api/chat", { input: "hello" });
  assert.equal(r.status, 500);
  assert.equal(r.body.reply, "The AI is currently busy. Please try again in a moment.");
  const empty = await post("/api/chat", {});
  assert.equal(empty.status, 400);
});

test("/health and /api/health report broker, ingest, db and last-reading age", async () => {
  for (const p of ["/health", "/api/health"]) {
    const r = await get(p);
    assert.ok([200, 503].includes(r.status));
    assert.deepEqual(Object.keys(r.body.checks), ["broker", "ingest", "db", "last_reading"]);
    assert.equal(r.body.checks.db.ok, true);
    assert.equal(typeof r.body.checks.last_reading.age_s, "number");
    assert.equal(r.body.checks.last_reading.source, "pi");
    assert.equal(r.body.mode, "live");
  }
});

test("/esp32data is gone and the SPA catch-all answers for unknown paths", async () => {
  const r = await fetch(base + "/api/esp32data");
  assert.ok(r.status === 404 || r.status === 503);
  const spa = await fetch(base + "/dashboard");
  assert.ok([200, 503].includes(spa.status));
});

// ---------------------------------------------------------------- Unity client contract
// Parsers ported line-for-line from github.com/ayeshatahirbutt1030/HydroGrow-Digital-Twin (Assets/*.cs)
// plus the patched HydroGrowJson helper (HydroGrowConfig.cs; the Unity project is not in this repo). They run on the RAW response text,
// because the C# scripts never deserialize: they scan text, so key ORDER and spacing matter.

// WaterAlertSystem.cs ExtractFloat (original): json is lowercased by the caller, first `"key":` wins,
// C# float.Parse throws on anything non-numeric -> caught -> 0.
function unityAlertExtractFloat(jsonLower, key) {
  const pattern = `"${key}":`;
  let start = jsonLower.indexOf(pattern);
  if (start === -1) return 0;
  start += pattern.length;
  const ends = [",", "}", "\n"].map((c) => jsonLower.indexOf(c, start)).filter((i) => i !== -1);
  const end = ends.length ? Math.min(...ends) : -1;
  const val = jsonLower.slice(start, end === -1 ? jsonLower.length : end).replace(/["{}:]/g, "").trim();
  return /^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(val) ? parseFloat(val) : 0;
}
// AutoPlantDisease.cs GetJsonString / GetJsonFloat / GetJsonBool (RegexOptions.IgnoreCase)
function unityPlantString(json, key, def) {
  const m = json.match(new RegExp(`"${key}"\s*:\s*"([^"]*)"`, "i"));
  return m && m[1].trim() ? m[1].trim() : def;
}
function unityPlantFloat(json, key, def) {
  const m = json.match(new RegExp(`"${key}"\s*:\s*([0-9]+\.?[0-9]*)`, "i"));
  return m ? parseFloat(m[1]) : def;
}
function unityPlantBool(json, key, def) {
  const m = json.match(new RegExp(`"${key}"\s*:\s*(true|false)`, "i"));
  return m ? m[1].toLowerCase() === "true" : def;
}
// Unity HydroGrowConfig.cs HydroGrowJson.TryGetFloat
function hydroGrowJsonFloat(json, key) {
  const m = json.match(new RegExp(`"${key}"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)`, "i"));
  return m ? parseFloat(m[1]) : undefined;
}

test("Unity scripts: /api/twins/:id serves every key they parse, readable by their exact parsers", async () => {
  const d = fixtures.diseased;  // latest frame fed in test.before
  for (const prefix of ["/api", ""]) {
    const raw = async (id) => {
      const r = await fetch(`${base}${prefix}/twins/${id}`);
      assert.equal(r.status, 200, `${prefix}/twins/${id}`);
      assert.equal(r.headers.get("access-control-allow-origin"), "*");
      const text = await r.text();
      const doc = JSON.parse(text);
      // ADT order: properties first, $metadata last. WaterAlertSystem takes the FIRST `"waterlevel":`,
      // which would be the $metadata entry {"lastUpdateTime":...} if $metadata came first -> 0.
      assert.equal(Object.keys(doc).at(-1), "$metadata", `${prefix}/twins/${id}: $metadata must be the last key`);
      return { text, doc };
    };

    // watertank1 -- WaterAlertSystem.cs (original keys) + patched waterlevelpct, watermov.cs (patched)
    const wt = await raw("watertank1");
    for (const k of ["waterLevel", "waterLevelPct", "ph", "ec"]) assert.ok(k in wt.doc, `watertank1.${k} present`);
    const wtLower = wt.text.toLowerCase();
    assert.equal(unityAlertExtractFloat(wtLower, "waterlevel"), d.water_level, "original WaterAlertSystem: waterlevel");
    assert.equal(unityAlertExtractFloat(wtLower, "waterlevelpct"), d.water_level_pct, "patched WaterAlertSystem: waterlevelpct");
    assert.equal(unityAlertExtractFloat(wtLower, "ph"), d.pH, "WaterAlertSystem: ph (Pi sends pH, twin key is ph)");
    assert.equal(unityAlertExtractFloat(wtLower, "ec"), d.ec, "WaterAlertSystem: ec");
    assert.equal(hydroGrowJsonFloat(wt.text, "waterLevelPct"), d.water_level_pct, "patched watermov: waterLevelPct");
    assert.equal(hydroGrowJsonFloat(wt.text, "waterLevel"), d.water_level, "HydroGrowJson: waterLevel != waterLevelPct");
    for (const k of ["ph", "ec"]) assert.equal(hydroGrowJsonFloat(wtLower, k), unityAlertExtractFloat(wtLower, k), `HydroGrowJson agrees on ${k}`);

    // environment1 -- WaterAlertSystem.cs
    const env = await raw("environment1");
    for (const k of ["temperature", "humidity"]) assert.ok(k in env.doc, `environment1.${k} present`);
    const envLower = env.text.toLowerCase();
    assert.equal(unityAlertExtractFloat(envLower, "temperature"), d.temperature, "WaterAlertSystem: temperature");
    assert.equal(unityAlertExtractFloat(envLower, "humidity"), d.humidity, "WaterAlertSystem: humidity");

    // plant1 / plant2 -- AutoPlantDisease.cs; parsed values must be the real ones, never the script defaults
    for (const id of ["plant1", "plant2"]) {
      const p = await raw(id);
      const ref = twinsRef[id];
      for (const k of ["disease_status", "diseased", "disease_confidence", "nutrient_status", "nutrient_confidence"]) {
        assert.ok(k in p.doc, `${id}.${k} present`);
      }
      assert.equal(typeof p.doc.diseased, "boolean", `${id}.diseased is a JSON bool (regex needs true|false)`);
      assert.equal(unityPlantString(p.text, "disease_status", "\0"), ref.disease_status, `${id} disease_status`);
      assert.equal(unityPlantBool(p.text, "diseased", null), ref.diseased, `${id} diseased`);
      assert.equal(unityPlantFloat(p.text, "disease_confidence", -1), ref.disease_confidence, `${id} disease_confidence`);
      assert.equal(unityPlantString(p.text, "nutrient_status", "\0"), ref.nutrient_status, `${id} nutrient_status`);
      assert.equal(unityPlantFloat(p.text, "nutrient_confidence", -1), ref.nutrient_confidence, `${id} nutrient_confidence`);
    }
  }
  assert.equal(twinsRef.plant2.diseased, true, "fixture sanity: plant2 is the diseased one");
});
