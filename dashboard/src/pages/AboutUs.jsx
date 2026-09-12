import React, { useState } from "react";
import ChatBot from "../components/ChatBot";

export default function AboutUs() {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className="container py-5" style={{ position: "relative", minHeight: "100vh" }}>
      <h2 className="text-center fw-bold mb-5">
        About Our Smart DWC System
      </h2>

      <div className="row justify-content-center align-items-start">
      
        <div className="col-md-5 mb-4 mb-md-0 text-center mt-md-4">
          <img 
            src={require('../assets/images/dwc_plant.png')} 
            alt="DWC Hydroponic System" 
            className="img-fluid shadow-lg"
            style={{ 
              borderRadius: "20px", 
              border: "5px solid #fff", 
              maxHeight: "450px",
              objectFit: "cover" 
            }}
          />
        </div>

        <div className="col-md-6">
          <div className="card border-0 shadow-sm p-4" style={{ borderRadius: "15px", backgroundColor: "#f9fffb" }}>
            <h4 className="text-success mb-3">Our Smart Farming Solution</h4>
            <p className="mb-4">
              Our flagship product is an <strong>IoT-Powered Deep Water Culture (DWC) Kit</strong> designed for both home hobbyists and commercial growers. 
              Unlike traditional kits, ours integrates high-precision sensors that communicate directly with our platform.
            </p>
            
            <p>
              By suspending plant roots in a nutrient-rich, hyper-oxygenated water reservoir, our system removes the "friction" of soil, allowing your plants to focus 100% of their energy on growth.
            </p>

            <hr className="my-4" />

            <h5 className="text-success mb-3">What makes us different?</h5>
            <ul className="list-unstyled">
              <li className="mb-3">
                📡 <strong>Real-Time Monitoring:</strong> Track pH, Water Temperature, and EC levels from your smartphone.
              </li>
              <li className="mb-3">
                ⚡ <strong>Automated Aeration:</strong> Smart air pumps that adjust based on oxygen saturation levels.
              </li>
              <li className="mb-3">
                🌿 <strong>Sustainable Design:</strong> Uses 90% less water than traditional soil and reduces the need for pesticides.
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div style={{ position: "fixed", bottom: "30px", right: "30px", zIndex: 1000 }}>
        
        {!chatOpen && (
          <div style={{
            position: "absolute",
            bottom: "85px",
            right: "0",
            width: "200px",
            background: "#fff",
            padding: "12px",
            borderRadius: "18px",
            boxShadow: "0 5px 15px rgba(0,0,0,0.1)",
            fontSize: "14px",
            fontWeight: "bold",
            color: "#16a34a",
            textAlign: "center",
            border: "2px solid #16a34a",
            animation: "pulse 2s infinite",
            pointerEvents: "none"
          }}>
            Ask about our product!
            <div style={{
              position: "absolute",
              bottom: "-10px",
              right: "25px",
              width: "0",
              height: "0",
              borderLeft: "10px solid transparent",
              borderRight: "10px solid transparent",
              borderTop: "10px solid #16a34a"
            }}></div>
          </div>
        )}

        <div
          onClick={() => setChatOpen(!chatOpen)}
          style={{
            width: "65px",
            height: "65px",
            borderRadius: "50%",
            backgroundColor: "#16a34a",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            cursor: "pointer",
            boxShadow: "0 8px 25px rgba(22, 163, 74, 0.4)",
            fontSize: "30px",
            transition: "all 0.3s ease",
            border: "4px solid white"
          }}
          onMouseEnter={(e) => e.currentTarget.style.transform = "scale(1.1)"}
          onMouseLeave={(e) => e.currentTarget.style.transform = "scale(1)"}
        >
          {chatOpen ? "✕" : "🌱"}
        </div>

        {chatOpen && (
          <div style={{
            position: "absolute",
            bottom: "85px",
            right: "0",
            width: "350px",
            height: "500px",
            backgroundColor: "#fff",
            borderRadius: "20px",
            display: "flex",
            flexDirection: "column",
            boxShadow: "0 15px 40px rgba(0,0,0,0.2)",
            overflow: "hidden",
            border: "1px solid #e2e8f0"
          }}>
            <div style={{ background: "#16a34a", color: "white", padding: "15px", fontWeight: "bold" }}>
              Hydroponics Assistant
            </div>
            <div style={{ flex: 1, overflowY: "auto", position: "relative" }}>
              <ChatBot />
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes pulse {
          0% { transform: translateY(0); }
          50% { transform: translateY(-5px); }
          100% { transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
