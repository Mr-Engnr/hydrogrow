const express = require("express");
const router = express.Router();
const telemetry = require("../services/telemetry.service");

// Mirrors the Azure Function get_twin: anonymous, CORS *, ADT document shape.
// Shape is produced in one place (telemetry.service.twin) so it is easy to adjust
// once the Unity parser script is available.
const cors = (res) => res.set("Access-Control-Allow-Origin", "*");

router.get("/twins", (req, res) => {
  cors(res);
  return res.json({ twins: telemetry.twinIds() });
});

router.get("/twins/:twinId", (req, res) => {
  cors(res);
  try {
    const doc = telemetry.twin(req.params.twinId);
    if (!doc) {
      // ADT returned 404 DigitalTwinNotFound; the Function wrapped every error as 500 {error}.
      return res.status(500).json({ error: `DigitalTwinNotFound: ${req.params.twinId}` });
    }
    return res.json(doc);
  } catch (error) {
    return res.status(500).json({ error: String(error.message || error) });
  }
});

module.exports = router;
