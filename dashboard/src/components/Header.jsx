import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js'; 
import React from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import './Header.css';

export default function Header() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  const isActive = (path) => location.pathname === path;

  return (
    <header className="header-modern">
      <nav className="navbar navbar-expand-lg">
        <div className="container">
          
          <Link className="header-logo" to="/">
            <span className="logo-icon">🌱</span>
            <span className="logo-text">HydroGrow</span>
          </Link>

          <button 
            className="navbar-toggler" 
            type="button" 
            data-bs-toggle="collapse" 
            data-bs-target="#navbarNav"
            aria-controls="navbarNav" 
            aria-expanded="false" 
            aria-label="Toggle navigation"
          >
            <span className="navbar-toggler-icon"></span>
          </button>

          <div className="collapse navbar-collapse" id="navbarNav">
            <ul className="nav-links ms-auto">
              <li className="nav-item">
                <Link className={`nav-link-custom ${isActive('/') ? 'active' : ''}`} to="/">
                  Home
                </Link>
              </li>

              <li className="nav-item">
                <Link className={`nav-link-custom ${isActive('/aboutus') ? 'active' : ''}`} to="/aboutus">
                  About Us
                </Link>
              </li>

              <li className="nav-item">
                <Link className={`nav-link-custom ${isActive('/dashboard') ? 'active' : ''}`} to="/dashboard">
                  Dashboard
                </Link>
              </li>

              <li className="nav-item">
                <Link className={`nav-link-custom ${isActive('/contact') ? 'active' : ''}`} to="/contact">
                  Contact
                </Link>
              </li>
            </ul>

            <div className="user-section">
              {isAuthenticated ? (
                <>
                  <div className="user-greeting">
                    <div className="user-avatar">
                      {user?.name?.charAt(0).toUpperCase()}
                    </div>
                    <span>Hello, {user?.name?.split(' ')[0]}</span>
                  </div>
                  <button 
                    className="btn-header btn-logout" 
                    onClick={handleLogout}
                  >
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <Link className="btn-header btn-header-outline" to="/login">
                    Sign In
                  </Link>
                  <Link className="btn-header btn-header-solid" to="/register">
                    Get Started
                  </Link>
                </>
              )}
            </div>
          </div>

        </div>
      </nav>
    </header>
  );
}
