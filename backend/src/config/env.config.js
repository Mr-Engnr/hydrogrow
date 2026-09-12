require("dotenv").config();

module.exports = {
  PORT: process.env.PORT || 5000,
  HUGGINGFACE_API_KEY: process.env.HF_API_KEY,
  HUGGINGFACE_MODEL: process.env.HF_MODEL || "meta-llama/Llama-3.2-3B-Instruct",
  ESP32_API_URL: process.env.ESP32_API_URL || "https://esp32-blob-api-b8f0gughdegvd9bb.centralindia-01.azurewebsites.net/api/getEsp32Data",
  AZURE_STORAGE_CONNECTION_STRING: process.env.AZURE_STORAGE_CONNECTION_STRING,
  AZURE_CONTAINER_NAME: process.env.AZURE_CONTAINER_NAME || "telemetry-data"
};
