import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap-icons/font/bootstrap-icons.css';
import React from "react";
import './Services.css';

const services = [
  {
    icon: 'bi-eye',
    iconClass: 'icon-green',
    title: 'Smart Monitoring',
    description: 'Real-time monitoring of pH, temperature, humidity, and water levels through IoT sensors.',
    tag: 'IoT Powered'
  },
  {
    icon: 'bi-droplet-fill',
    iconClass: 'icon-blue',
    title: 'Automated Nutrient Control',
    description: 'Automatically adjusts nutrients and water flow to ensure optimal plant growth.',
    tag: 'Auto-Balance'
  },
  {
    icon: 'bi-shield-check',
    iconClass: 'icon-purple',
    title: 'Disease Detection',
    description: 'AI-powered plant disease detection to prevent losses and maintain healthy crops.',
    tag: 'AI Enabled'
  },
  {
    icon: 'bi-phone',
    iconClass: 'icon-orange',
    title: 'Remote System Control',
    description: 'Control and monitor your hydroponic system remotely for effortless management.',
    tag: 'Mobile Ready'
  },
  {
    icon: 'bi-cloud-arrow-up-fill',
    iconClass: 'icon-teal',
    title: 'Cloud Data Storage',
    description: 'Secure cloud storage for all your sensor data, accessible anytime via the app.',
    tag: 'Secure Cloud'
  },
  {
    icon: 'bi-moisture',
    iconClass: 'icon-pink',
    title: 'Automated Irrigation',
    description: 'Smart water flow management ensures plants get the right amount at the right time.',
    tag: 'Smart Flow'
  }
];

export default function Services() {
  return (
    <section className="services-section">
      <div className="container">
        <div className="services-header">
          <span className="badge-text">What We Offer</span>
          <h2>Our Premium Services</h2>
          <p>Experience the future of hydroponic farming with our smart, automated solutions</p>
        </div>
        <div className="row g-4">
          {services.map((service, index) => (
            <div className="col-lg-4 col-md-6" key={index}>
              <div className="service-card text-center">
                <div className={`service-icon ${service.iconClass}`}>
                  <i className={`bi ${service.icon}`}></i>
                </div>
                <h5>{service.title}</h5>
                <p>{service.description}</p>
                <span className="feature-tag">{service.tag}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
