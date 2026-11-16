const express = require("express");
const router = express.Router();
const telemetry = require("../services/telemetry.service");
const { SENSOR_INTERVAL_S } = require("../config/env.config");

// Public, exactly as before. Same one-element array, same remap.
router.get("/pidata", (req, res) => {
  try {
    const found = telemetry.latest();
    if (!found) {
      return res.status(404).json({ error: "No data found" });
    }
    return res.json([telemetry.remapForDashboard(found.data)]);
  } catch (error) {
    console.error("Error fetching Pi data:", error.message);
    return res.status(500).json({ error: error.message });
  }
});

// Expo helper for the dashboard badge and "last updated" indicator: which source
// produced the latest reading and how old it is. Not part of the Azure contract;
// the dashboard treats a failure as "unknown" (never as Live).
//   source: "pi" (real firmware) | "fake" (tools/fake_pi.py) | "replay" (tools/replay.py)
//   stale_after_s: 2 x SENSOR_INTERVAL_S, the amber threshold
router.get("/pidata/source", (req, res) => {
  try {
    const found = telemetry.latest();
    const staleAfter = 2 * SENSOR_INTERVAL_S;
    if (!found) {
      return res.json({ source: null, age_s: null, ingested_at: null, stale_after_s: staleAfter,
                        status: null, dry_run: false, pi_timestamp: null });
    }
    const age = (Date.now() - Date.parse(found.row.ingested_at + "Z")) / 1000;
    return res.json({
      source: found.row.source,
      age_s: Math.round(age),
      ingested_at: found.row.ingested_at,
      stale_after_s: staleAfter,
      status: found.row.status ?? null,
      dry_run: found.data.dry_run === true,
      pi_timestamp: found.row.pi_timestamp ?? null,
    });
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
});

module.exports = router;
