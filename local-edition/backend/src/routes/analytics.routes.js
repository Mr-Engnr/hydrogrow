const express = require("express");
const router = express.Router();
const telemetry = require("../services/telemetry.service");

// Same query handling as the old proxy, same body as the Azure Function.
router.get("/analytics", (req, res) => {
  try {
    const parsedDays = Number.parseInt(req.query.days, 10);
    const days = Number.isNaN(parsedDays) || parsedDays <= 0 ? 7 : parsedDays;
    return res.json(telemetry.analytics(days));
  } catch (error) {
    return res.status(500).json({ error: "Failed to fetch analytics data" });
  }
});

module.exports = router;
