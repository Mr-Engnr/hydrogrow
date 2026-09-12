const axios = require("axios");
const { HUGGINGFACE_API_KEY, HUGGINGFACE_MODEL } = require("../config/env.config");

class HuggingFaceService {
  constructor() {
    this.apiUrl = "https://router.huggingface.co/v1/chat/completions";
    this.model = HUGGINGFACE_MODEL;
  }

  async getChatResponse(userInput) {
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
          }
        }
      );

      return response.data.choices[0].message.content;
    } catch (error) {
      throw error;
    }
  }
}

module.exports = new HuggingFaceService();
