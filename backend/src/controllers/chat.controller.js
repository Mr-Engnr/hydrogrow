const huggingFaceService = require("../services/huggingface.service");

exports.handleChatRequest = async (req, res) => {
  const { input } = req.body;
  console.log("Message received from React:", input);

  if (!input) {
    return res.status(400).json({ error: "Input is required" });
  }

  try {
    const botReply = await huggingFaceService.getChatResponse(input);
    res.json({ reply: botReply });
  } catch (err) {
    const errorMsg = err.response?.data || err.message;
    console.error("❌ Hugging Face API Error:", errorMsg);
    res.status(500).json({ 
      reply: "The AI is currently busy. Please try again in a moment.",
      details: errorMsg 
    });
  }
};
