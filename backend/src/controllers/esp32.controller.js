const esp32Service = require("../services/esp32.service");

exports.getESP32Data = async (req, res) => {
  try {
    const data = await esp32Service.getESP32Data();
    res.json(data);
  } catch (err) {
    console.error("❌ Error fetching ESP32 data:", err.message);
    res.status(500).json({ error: "ESP32 data not available yet" });
  }
};
