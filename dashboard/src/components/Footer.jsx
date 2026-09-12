import { Link } from 'react-router-dom';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';
import './Footer.css';

export default function Footer() {
  return (
    <footer className="footer-modern">
      <div className="footer-content">
        <div className="container">
          <div className="row g-4">

            {/* Company Info */}
            <div className="col-lg-4 col-md-6">
              <div className="footer-brand">
                <div className="brand-logo">
                  <span className="logo-icon">🌱</span>
                  <h3>HydroGrow</h3>
                </div>
                <p className="brand-description">
                  Smart hydroponics solution using IoT technology to monitor plant health, 
                  nutrients, and water conditions in real time.
                </p>
                <div className="social-links">
                  <a href="https://instagram.com/hydrogrow.pk" target="_blank" rel="noopener noreferrer" className="social-link instagram">
                    <span>📷</span>
                  </a>
                  <a href="#" className="social-link" title="Coming Soon">
                    <span>📘</span>
                  </a>
                  <a href="#" className="social-link" title="Coming Soon">
                    <span>🐦</span>
                  </a>
                </div>
              </div>
            </div>

            {/* Quick Links */}
            <div className="col-6 col-lg-2 col-md-6">
              <div className="footer-section">
                <h4 className="footer-title">Quick Links</h4>
                <ul className="footer-links">
                  <li><Link to="/">Home</Link></li>
                  <li><Link to="/about">About Us</Link></li>
                  <li><Link to="/dashboard">Dashboard</Link></li>
                  <li><Link to="/contact">Contact</Link></li>
                </ul>
              </div>
            </div>

            {/* Services */}
            <div className="col-6 col-lg-3 col-md-6">
              <div className="footer-section">
                <h4 className="footer-title">Services</h4>
                <ul className="footer-links">
                  <li><span>🔬</span> Smart Nutrient Systems</li>
                  <li><span>📡</span> IoT Hydroponic Kits</li>
                  <li><span>📊</span> Real-Time Monitoring</li>
                  <li><span>🤖</span> AI Plant Assistant</li>
                </ul>
              </div>
            </div>

            {/* Newsletter */}
            <div className="col-lg-3 col-md-6">
              <div className="footer-section">
                <h4 className="footer-title">Stay Updated</h4>
                <p className="newsletter-text">
                  Get the latest farming tips and updates.
                </p>
                <div className="newsletter-form">
                  <input
                    type="email"
                    placeholder="Your email"
                    className="newsletter-input"
                  />
                  <button className="newsletter-btn">
                    <span>→</span>
                  </button>
                </div>
                <div className="contact-info">
                  <p><span>📍</span> Silicon Valley of Lahore, Pakistan</p>
                  <p><span>📧</span> hello@hydrogrow.pk</p>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="footer-bottom">
        <div className="container">
          <div className="bottom-content">
            <span className="copyright">
              © 2026 HydroGrow. Crafted with 💚 in Pakistan
            </span>
            <div className="bottom-links">
              <Link to="/privacy">Privacy Policy</Link>
              <Link to="/terms">Terms of Service</Link>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}