const path = require("path");
// Load the shared repo-root .env first (what systemd uses), then a local backend/.env if present.
require("dotenv").config({ path: path.join(__dirname, "../../../.env"), quiet: true });
require("dotenv").config({ quiet: true });

const DEFAULT_DB = path.join(__dirname, "../../../data/hydrogrow.db");

module.exports = {
  PORT: parseInt(process.env.PORT || "8080", 10),
  NODE_ENV: process.env.NODE_ENV || "production",
  DB_PATH: process.env.HYDROGROW_DB || DEFAULT_DB,
  SCHEMA_PATH: path.join(__dirname, "../../../ingest/schema.sql"),
  BUILD_DIR: process.env.DASHBOARD_BUILD_DIR || path.join(__dirname, "../../build"),
  HUGGINGFACE_API_KEY: process.env.HF_API_KEY,
  HUGGINGFACE_MODEL: process.env.HF_MODEL || "Qwen/Qwen2.5-7B-Instruct",
  DEMO_USER_EMAIL: process.env.DEMO_USER_EMAIL,
  DEMO_USER_PASSWORD: process.env.DEMO_USER_PASSWORD,
  DEMO_USER_NAME: process.env.DEMO_USER_NAME || "Expo Demo",
  HEALTH_STALE_AFTER_S: parseInt(process.env.HEALTH_STALE_AFTER_S || "120", 10),
  // Shared with main.py via the same .env; the dashboard turns its "last updated"
  // indicator amber after 2x this with no new reading.
  SENSOR_INTERVAL_S: parseInt(process.env.SENSOR_INTERVAL_S || "1800", 10),
  MQTT_HOST: process.env.MQTT_HOST || "127.0.0.1",
  MQTT_PORT: parseInt(process.env.MQTT_PORT || "1883", 10),
  MQTT_WS_PORT: parseInt(process.env.MQTT_WS_PORT || "9001", 10),
};
