import React, { useState, useEffect, useRef } from "react";
import apiService from "../services/api.service";

export default function ChatBot() {
  const [messages, setMessages] = useState([
    { type: "bot", text: "Hello! Ask me anything about hydroponics." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userInput = input;
    setMessages(prev => [...prev, { type: "user", text: userInput }]);
    setInput("");
    setLoading(true);

    try {
      const data = await apiService.sendChatMessage(userInput);
      let botReply = data.reply;

      if (botReply.toLowerCase().startsWith(userInput.toLowerCase())) {
        botReply = botReply.substring(userInput.length).trim();
      }
      
      botReply = botReply.replace(/^(bot:|assistant:|ai:|answer:)/i, "").trim();
      
      if (botReply.length > 500) {
        botReply = botReply.substring(0, 500) + "...";
      }

      setMessages(prev => [...prev, { type: "bot", text: botReply }]);
    } catch (err) {
      console.error("Frontend Error:", err);
      setMessages(prev => [...prev, { type: "bot", text: "Error: Could not reach the AI server." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%", 
        width: "100%",
        padding: "15px",
        backgroundColor: "#fff"
      }}
    >
      <div
        style={{
          flex: 1,
          overflowY: "auto", 
          paddingRight: "5px",
          fontSize: "0.95rem",
          display: "flex",
          flexDirection: "column"
        }}
      >
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              marginBottom: "12px",
              textAlign: msg.type === "user" ? "right" : "left"
            }}
          >
            <div
              style={{
                display: "inline-block",
                padding: "10px 14px",
                borderRadius: "15px",
                background: msg.type === "user" ? "#16a34a" : "#f1f5f9",
                color: msg.type === "user" ? "white" : "#1e293b",
                border: msg.type === "user" ? "none" : "1px solid #e2e8f0",
                maxWidth: "85%",
                wordWrap: "break-word",
                boxShadow: "0 1px 2px rgba(0,0,0,0.05)"
              }}
            >
              {msg.text}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ textAlign: "left", color: "#64748b", fontSize: "0.8rem", marginLeft: "5px" }}>
            🌱 Typing...
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <div style={{ display: "flex", gap: "8px", paddingTop: "10px", borderTop: "1px solid #eee" }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleSend()}
          placeholder="Type your message..."
          disabled={loading}
          style={{
            flex: 1,
            padding: "10px",
            borderRadius: "20px",
            border: "1px solid #cbd5e1",
            outline: "none",
            fontSize: "14px"
          }}
        />
        <button
          onClick={handleSend}
          disabled={loading}
          style={{
            padding: "8px 15px",
            borderRadius: "20px",
            border: "none",
            background: "#16a34a",
            color: "white",
            cursor: "pointer",
            fontWeight: "bold"
          }}
        >
          Send
        </button>
      </div>
    </div>
  );
}