const express = require("express");
const axios = require("axios");

const router = express.Router();

router.get("/analytics", async (req, res) => {
  try {
    const parsedDays = Number.parseInt(req.query.days, 10);
    const days = Number.isNaN(parsedDays) || parsedDays <= 0 ? 7 : parsedDays;

    const azureFunctionUrl = process.env.AZURE_FUNCTION_URL;
    if (!azureFunctionUrl) {
      return res.status(500).json({ error: "AZURE_FUNCTION_URL is not configured" });
    }

    const response = await axios.get(`${azureFunctionUrl}&days=${days}`);

    return res.json(response.data);
  } catch (error) {
    const statusCode = error.response?.status || 500;
    const message = error.response?.data || { error: "Failed to fetch analytics data" };
    return res.status(statusCode).json(message);
  }
});

module.exports = router;