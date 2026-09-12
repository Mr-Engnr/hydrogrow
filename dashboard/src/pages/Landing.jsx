import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';
import React, { useState } from "react";
import { Link } from "react-router-dom";
import Services from "../components/Services";
import './Landing.css';

export default function Landing() {
  const [showMore, setShowMore] = useState(false);

  return (
    <>
      {/* Hero Section */}
      <section className="hero-section">
        <div className="container">
          <div className="row align-items-center">
            <div className="col-lg-6 mb-4 mb-lg-0">
              <div className="hero-content">
                <div className="hero-badge">
                  <span className="hero-badge-icon">🌿</span>
                  <span>Smart Hydroponic Solutions</span>
                </div>
                
                <h1 className="hero-title">
                  Grow Smarter with <span className="highlight">HydroGrow</span> Technology
                </h1>
                
                <p className="hero-description">
                  Experience the future of farming with our IoT-powered hydroponic system. 
                  Real-time monitoring, automated control, and AI-driven insights for optimal plant growth.
                </p>
                
                <div className="hero-buttons">
                  <Link to="/register" className="btn-hero btn-hero-primary">
                    Get Started Free
                    <span>→</span>
                  </Link>
                  <Link to="/dashboard" className="btn-hero btn-hero-secondary">
                    View Dashboard
                  </Link>
                </div>
                
                <div className="hero-stats">
                  <div className="stat-item">
                    <div className="stat-number">98%</div>
                    <div className="stat-label">Water Saved</div>
                  </div>
                  <div className="stat-item">
                    <div className="stat-number">3x</div>
                    <div className="stat-label">Faster Growth</div>
                  </div>
                  <div className="stat-item">
                    <div className="stat-number">24/7</div>
                    <div className="stat-label">Monitoring</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="col-lg-6">
              <div className="hero-video-wrapper">
                <div className="video-card">
                  <div className="ratio ratio-16x9">
                    <iframe 
                      src="https://www.youtube.com/embed/UMasKCR_o3Q" 
                      title="Introduction to Hydroponic farming" 
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" 
                      referrerPolicy="strict-origin-when-cross-origin" 
                      allowFullScreen
                    ></iframe>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Services Section */}
      <Services />

      {/* Feature Section */}
      <section className="feature-section">
        <div className="container">
          <div className="row align-items-center g-5">
            <div className="col-lg-6">
              <div className="feature-image">
                <img
                  src={require('../assets/images/image2.jpg')}
                  alt="HydroGrow System"
                />
              </div>
            </div>
            <div className="col-lg-6">
              <div className="feature-content">
                <span className="feature-label">Why Choose Us</span>
                <h2 className="feature-title">
                  Complete Hydroponic Management System
                </h2>
                <p className="feature-text">
                  HydroGrow brings modern automation to your garden or indoor space. 
                  Our smart system monitors and controls every aspect of plant growth 
                  for maximum yield with minimum effort.
                </p>
                
                {showMore && (
                  <p className="feature-text">
                    With real-time monitoring of nutrients, pH, temperature, and humidity, 
                    HydroGrow ensures optimal growing conditions. Our AI-powered system 
                    detects plant diseases early and provides actionable insights for 
                    sustainable, soil-less farming.
                  </p>
                )}
                
                <ul className="feature-list">
                  <li>
                    <span className="feature-list-icon">✓</span>
                    Real-time pH & nutrient monitoring
                  </li>
                  <li>
                    <span className="feature-list-icon">✓</span>
                    Automated water flow management
                  </li>
                  <li>
                    <span className="feature-list-icon">✓</span>
                    AI-powered disease detection
                  </li>
                  <li>
                    <span className="feature-list-icon">✓</span>
                    Mobile app remote control
                  </li>
                </ul>
                
                <button 
                  className="btn-hero btn-hero-primary mt-4"
                  onClick={() => setShowMore(!showMore)}
                  style={{ background: 'linear-gradient(135deg, #228B22, #2d5a3d)', color: 'white' }}
                >
                  {showMore ? "Show Less" : "Discover More"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-section">
        <div className="container">
          <h2 className="cta-title">Ready to Start Growing?</h2>
          <p className="cta-text">
            Join thousands of smart farmers using HydroGrow to revolutionize their hydroponic systems.
          </p>
          <Link to="/register" className="btn-hero btn-hero-primary">
            Create Free Account
            <span>→</span>
          </Link>
        </div>
      </section>
    </>
  );
}
