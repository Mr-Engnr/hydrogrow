const axios = require("axios");
const { HUGGINGFACE_API_KEY, HUGGINGFACE_MODEL } = require("../config/env.config");

class HuggingFaceService {
  constructor() {
    this.apiUrl = "https://router.huggingface.co/v1/chat/completions";
    this.model = HUGGINGFACE_MODEL;
  }

  async getChatResponse(userInput) {
    if (!HUGGINGFACE_API_KEY) {
      // Optional feature: no key means no outbound call. The controller turns
      // this into the same "AI is currently busy" reply the UI already handles.
      const err = new Error("HF_API_KEY not configured; chat is disabled offline");
      err.offline = true;
      throw err;
    }
    try {
      const response = await axios.post(
        this.apiUrl,
        {
          model: this.model,
          messages: [
            { role: "system", content: "You are a helpful assistant specializing in hydroponics." },
            { role: "user", content: userInput }
          ],
          max_tokens: 500
        },
        {
          headers: {
            Authorization: `Bearer ${HUGGINGFACE_API_KEY}`,
            "Content-Type": "application/json"
          },
          timeout: 15000   // offline hotspot: fail fast instead of hanging the UI
        }
      );

      return response.data.choices[0].message.content;
    } catch (error) {
      throw error;
    }
  }
}

module.exports = new HuggingFaceService();
