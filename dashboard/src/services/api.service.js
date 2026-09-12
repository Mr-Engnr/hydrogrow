import axios from "axios";

// Use backend URL directly in development, relative path in production
const API_BASE_URL = process.env.NODE_ENV === 'production' 
  ? "/api" 
  : "http://localhost:5000/api";

class ApiService {
  getAuthHeader() {
    const token = localStorage.getItem('authToken');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async sendChatMessage(input) {
    try {
      const response = await axios.post(`${API_BASE_URL}/chat`, { input });
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  async getRaspberryPiData() {
    try {
      const response = await axios.get(`${API_BASE_URL}/pidata`, {
        headers: this.getAuthHeader()
      });
      return response.data;
    } catch (error) {
      throw error;
    }
  }

  async getAnalytics(days = 7) {
    try {
      const response = await axios.get(`${API_BASE_URL}/analytics`, {
        params: { days }
      });
      return response.data;
    } catch (error) {
      throw error;
    }
  }
}

export default new ApiService();
