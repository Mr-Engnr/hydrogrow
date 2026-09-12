import React, { useState } from 'react';
import 'bootstrap/dist/css/bootstrap.min.css';
import './Contact.css';

export default function Contact() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    subject: '',
    message: ''
  });
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setLoading(true);
    
    // Simulate form submission
    setTimeout(() => {
      setSubmitted(true);
      setLoading(false);
      setFormData({ name: '', email: '', subject: '', message: '' });
    }, 1000);
  };

  return (
    <div className="contact-page">
      {/* Hero Section */}
      <section className="contact-hero">
        <div className="container">
          <div className="hero-content">
            <h1>Get In Touch</h1>
            <p>Have questions about HydroGrow? We'd love to hear from you!</p>
          </div>
        </div>
      </section>

      {/* Contact Content */}
      <section className="contact-content py-5">
        <div className="container">
          <div className="row g-5">
            {/* Contact Info */}
            <div className="col-lg-5">
              <div className="contact-info">
                <h2>Contact Information</h2>
                <p className="info-subtitle">
                  Fill out the form and our team will get back to you within 24 hours.
                </p>

                <div className="info-items">
                  <div className="info-item">
                    <div className="info-icon">📍</div>
                    <div className="info-text">
                      <h4>Address</h4>
                      <p>Silicon Valley of Lahore<br />Pakistan</p>
                    </div>
                  </div>

                  <div className="info-item">
                    <div className="info-icon">📧</div>
                    <div className="info-text">
                      <h4>Email</h4>
                      <p>support@hydrogrow.com<br />sales@hydrogrow.com</p>
                    </div>
                  </div>

                  <div className="info-item">
                    <div className="info-icon">📞</div>
                    <div className="info-text">
                      <h4>Phone</h4>
                      <p>+92 (555) 123-4567<br />Mon - Fri, 9am - 6pm</p>
                    </div>
                  </div>
                </div>

                <div className="social-links">
                  <h4>Follow Us</h4>
                  <div className="social-icons">
                    <a href="https://instagram.com/hydrogrow.pk" target="_blank" rel="noopener noreferrer" className="social-icon instagram" aria-label="Instagram">
                      <span>📷</span>
                      <span className="social-handle">@hydrogrow.pk</span>
                    </a>
                  </div>
                </div>
              </div>
            </div>

            {/* Contact Form */}
            <div className="col-lg-7">
              <div className="contact-form-card">
                {submitted ? (
                  <div className="success-message">
                    <div className="success-icon">✅</div>
                    <h3>Message Sent!</h3>
                    <p>Thank you for reaching out. We'll get back to you soon.</p>
                    <button 
                      className="btn-send-another"
                      onClick={() => setSubmitted(false)}
                    >
                      Send Another Message
                    </button>
                  </div>
                ) : (
                  <>
                    <h2>Send us a Message</h2>
                    <form onSubmit={handleSubmit} className="contact-form">
                      <div className="row g-3">
                        <div className="col-md-6">
                          <div className="form-group">
                            <label htmlFor="name">Full Name</label>
                            <input
                              type="text"
                              id="name"
                              name="name"
                              value={formData.name}
                              onChange={handleChange}
                              placeholder="John Doe"
                              required
                            />
                          </div>
                        </div>
                        <div className="col-md-6">
                          <div className="form-group">
                            <label htmlFor="email">Email Address</label>
                            <input
                              type="email"
                              id="email"
                              name="email"
                              value={formData.email}
                              onChange={handleChange}
                              placeholder="you@example.com"
                              required
                            />
                          </div>
                        </div>
                        <div className="col-12">
                          <div className="form-group">
                            <label htmlFor="subject">Subject</label>
                            <input
                              type="text"
                              id="subject"
                              name="subject"
                              value={formData.subject}
                              onChange={handleChange}
                              placeholder="How can we help?"
                              required
                            />
                          </div>
                        </div>
                        <div className="col-12">
                          <div className="form-group">
                            <label htmlFor="message">Message</label>
                            <textarea
                              id="message"
                              name="message"
                              value={formData.message}
                              onChange={handleChange}
                              placeholder="Tell us more about your inquiry..."
                              rows="5"
                              required
                            ></textarea>
                          </div>
                        </div>
                        <div className="col-12">
                          <button 
                            type="submit" 
                            className={`submit-btn ${loading ? 'loading' : ''}`}
                            disabled={loading}
                          >
                            {loading ? (
                              <>
                                <span className="spinner"></span>
                                Sending...
                              </>
                            ) : (
                              <>
                                Send Message
                                <span className="btn-arrow">→</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </form>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Map Section */}
      <section className="map-section">
        <div className="container">
          <div className="map-placeholder">
            <div className="map-overlay">
              <span>🗺️</span>
              <p>Interactive Map Coming Soon</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
