const express = require("express");
const net = require("net");
const router = express.Router();
const telemetry = require("../services/telemetry.service");
const { MQTT_HOST, MQTT_PORT, MQTT_WS_PORT, HEALTH_STALE_AFTER_S, DB_PATH } = require("../config/env.config");

const STARTED_AT = new Date();

function brokerReachable(timeoutMs = 800) {
  return new Promise((resolve) => {
    const sock = net.connect({ host: MQTT_HOST, port: MQTT_PORT });
    const done = (ok) => { sock.destroy(); resolve(ok); };
    sock.setTimeout(timeoutMs, () => done(false));
    sock.once("connect", () => done(true));
    sock.once("error", () => done(false));
  });
}

// GET /health  (also mounted at /api/health). 200 when everything is up, 503 otherwise.
router.get("/health", async (req, res) => {
  const now = Date.now();
  const checks = { broker: { ok: false }, ingest: { ok: false }, db: { ok: false }, last_reading: { ok: false } };

  checks.broker.ok = await brokerReachable();
  checks.broker.target = `${MQTT_HOST}:${MQTT_PORT}`;
  checks.broker.ws_port = MQTT_WS_PORT;

  try {
    const c = telemetry.counts();
    checks.db = { ok: true, path: DB_PATH, readings: c.n, first: c.first, last: c.last };
  } catch (e) {
    checks.db = { ok: false, error: e.message };
  }

  try {
    const st = telemetry.ingestState();
    if (st) {
      const age = (now - Date.parse(st.updated_at + "Z")) / 1000;
      checks.ingest = {
        ok: age < 30 && !st.stopped,
        heartbeat_age_s: Math.round(age),
        broker_connected: !!st.broker_connected,
        messages_stored: st.messages_stored,
        last_source: st.last_source,
      };
    } else {
      checks.ingest = { ok: false, error: "no heartbeat yet" };
    }
  } catch (e) {
    checks.ingest = { ok: false, error: e.message };
  }

  try {
    const found = telemetry.latest();
    if (found) {
      const age = (now - Date.parse(found.row.ingested_at + "Z")) / 1000;
      checks.last_reading = {
        ok: age <= HEALTH_STALE_AFTER_S,
        age_s: Math.round(age),
        stale_after_s: HEALTH_STALE_AFTER_S,
        source: found.row.source,
        status: found.row.status,
        blob_name: found.row.blob_name,
      };
    } else {
      checks.last_reading = { ok: false, error: "no readings" };
    }
  } catch (e) {
    checks.last_reading = { ok: false, error: e.message };
  }

  const ok = Object.values(checks).every((c) => c.ok);
  res.status(ok ? 200 : 503).json({
    ok,
    mode: checks.last_reading.source === "replay" ? "demo" : checks.last_reading.source === "fake" ? "fake" : "live",
    uptime_s: Math.round(process.uptime()),
    started_at: STARTED_AT.toISOString(),
    checks,
  });
});

module.exports = router;
