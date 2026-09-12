const express = require("express");
const router = express.Router();
const { BlobServiceClient } = require("@azure/storage-blob");
const { AZURE_STORAGE_CONNECTION_STRING, AZURE_CONTAINER_NAME } = require("../config/env.config");

router.get("/pidata", async (req, res) => {
  try {
    const blobServiceClient = BlobServiceClient.fromConnectionString(AZURE_STORAGE_CONNECTION_STRING);
    const containerClient = blobServiceClient.getContainerClient(AZURE_CONTAINER_NAME);

    let latestBlob = null;
    for await (const blob of containerClient.listBlobsFlat()) {
      // Only consider blobs that match sensor data naming pattern
      if (!blob.name.match(/^\d{8}_\d{6}_\d+\.json$/)) continue;
      if (!latestBlob || blob.name > latestBlob.name) {
        latestBlob = blob;
      }
    }

    if (!latestBlob) {
      return res.status(404).json({ error: "No data found" });
    }

    const blobClient = containerClient.getBlobClient(latestBlob.name);
    const downloadResponse = await blobClient.download();
    const chunks = [];
    for await (const chunk of downloadResponse.readableStreamBody) {
      chunks.push(chunk);
    }

    const data = JSON.parse(Buffer.concat(chunks).toString());
    console.log("RAW BLOB DATA:", JSON.stringify(data));
    const remapped = {
      ph: data.pH ?? data.ph ?? null,
      ec: data.ec,
      waterTemp: data.temperature,
      humidity: data.humidity,
      waterLevel: data.waterLevel ?? data.water_level ?? null,
      waterLevelPct: data.water_level_pct ?? null,
      waterLow: data.water_low ?? null,
      health_status: data.nutrient_status?.label || data.nutrient_status || "Unknown",
      nutrient_confidence: data.nutrient_confidence,
      plant1: data.plant1 || null,
      plant2: data.plant2 || null,
      plant3: data.plant3 || null,
      disease_predictions: data.disease_predictions || null,
    };
    return res.json([remapped]);

  } catch (error) {
    console.error("Error fetching Pi data:", error.message);
    return res.status(500).json({ error: error.message });
  }
});

module.exports = router;
