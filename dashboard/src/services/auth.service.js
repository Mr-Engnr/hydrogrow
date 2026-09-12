import axios from "axios";

// Use backend URL directly in development, relative path in production
const API_BASE_URL = process.env.NODE_ENV === 'production' 
  ? "/api" 
  : "http://localhost:5000/api";

class AuthServiceFrontend {
  async register(email, password, name) {
    try {
      const response = await axios.post(`${API_BASE_URL}/auth/register`, {
        email,
        password,
        name
      });
      return response.data;
    } catch (error) {
      return error.response?.data || { success: false, message: 'Registration failed' };
    }
  }

  async login(email, password) {
    try {
      const response = await axios.post(`${API_BASE_URL}/auth/login`, {
        email,
        password
      });
      return response.data;
    } catch (error) {
      return error.response?.data || { success: false, message: 'Login failed' };
    }
  }

  async logout(token) {
    try {
      const response = await axios.post(
        `${API_BASE_URL}/auth/logout`,
        {},
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      return response.data;
    } catch (error) {
      return { success: true }; // Always clear local state
    }
  }

  async getMe(token) {
    try {
      const response = await axios.get(`${API_BASE_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      return response.data;
    } catch (error) {
      return { success: false };
    }
  }

  getAuthHeader() {
    const token = localStorage.getItem('authToken');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}

export default new AuthServiceFrontend();
