const express = require("express");
const router = express.Router();
const chatRoutes = require("./chat.routes");
const pidataRoutes = require("./pidata.routes");
const analyticsRoutes = require("./analytics.routes");
const authRoutes = require("./auth.routes");
const twinsRoutes = require("./twins.routes");
const healthRoutes = require("./health.routes");

// Public routes, same mounting as before (/pidata stays public).
router.use("/auth", authRoutes);
router.use("/", chatRoutes);
router.use("/", pidataRoutes);
router.use("/", analyticsRoutes);
router.use("/", twinsRoutes);
router.use("/", healthRoutes);

// /esp32data (the only authMiddleware-protected data route) proxied a dead
// Azure URL and had no callers; dropped.

module.exports = router;
