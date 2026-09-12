const axios = require("axios");
const { ESP32_API_URL } = require("../config/env.config");

class ESP32Service {
  async getESP32Data() {
    try {
      const response = await axios.get(ESP32_API_URL);
      return response.data;
    } catch (error) {
      throw error;
    }
  }
}

module.exports = new ESP32Service();
