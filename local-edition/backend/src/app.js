const express = require("express");
const cors = require("cors");
const path = require("path");
const fs = require("fs");
const corsOptions = require("./config/cors.config");
const routes = require("./routes");
const twinsRoutes = require("./routes/twins.routes");
const healthRoutes = require("./routes/health.routes");
const { BUILD_DIR } = require("./config/env.config");

const app = express();

app.use(cors(corsOptions));
app.use(express.json());

// Serve the React build FIRST (before API routes), as before.
app.use(express.static(BUILD_DIR));

// API routes: /api/auth/*, /api/pidata, /api/analytics, /api/chat, /api/twins/:id, /api/health
app.use("/api", routes);

// Root aliases for non-dashboard clients: Unity polls /twins/:id, healthcheck.sh hits /health.
app.use("/", twinsRoutes);
app.use("/", healthRoutes);

// Unknown API paths are a JSON 404, never the SPA shell (keeps /api/esp32data dead).
app.all("/api/{*path}", (req, res) => {
  res.status(404).json({ error: `Not found: ${req.method} ${req.originalUrl}` });
});

// React catch-all (Express 5 wildcard syntax).
app.get("/{*path}", (req, res) => {
  const index = path.join(BUILD_DIR, "index.html");
  if (!fs.existsSync(index)) {
    return res.status(503).type("text").send("Dashboard build not found. Build it with: cd local-edition/dashboard && npm ci && npm run build  (output: " + BUILD_DIR + ")");
  }
  res.sendFile(index);
});

module.exports = app;
