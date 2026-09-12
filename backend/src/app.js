const express = require("express");
const cors = require("cors");
const corsOptions = require("./config/cors.config");
const routes = require("./routes");
const path = require("path");

const app = express();

// Middleware
app.use(cors(corsOptions));
app.use(express.json());

// Serve React frontend FIRST (before API routes)
app.use(express.static(path.join(__dirname, "../build")));

// API Routes
app.use("/api", routes);

// React catch-all
app.get("/{*path}", (req, res) => {
  res.sendFile(path.join(__dirname, "../build", "index.html"));
});

module.exports = app;
