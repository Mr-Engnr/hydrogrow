import axios from "axios";

// Same relative base as api.service.js: the Express backend serves both the
// dashboard and /api, so no host is ever baked into the bundle.
import { API_BASE_URL } from "./api.service";

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
