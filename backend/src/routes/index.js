const express = require("express");
const router = express.Router();
const chatRoutes = require("./chat.routes");
const esp32Routes = require("./esp32.routes");
const pidataRoutes = require("./pidata.routes");
const analyticsRoutes = require("./analytics.routes");
const authRoutes = require("./auth.routes");
const authMiddleware = require("../middleware/auth.middleware");

// Public routes
router.use("/auth", authRoutes);
router.use("/", chatRoutes);
router.use("/", pidataRoutes);
router.use("/", analyticsRoutes);

// Protected routes (require authentication)
router.use("/", authMiddleware, esp32Routes);

module.exports = router;
