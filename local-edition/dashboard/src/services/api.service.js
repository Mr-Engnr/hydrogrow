import axios from "axios";

// The dashboard is served by the same Express process that answers /api, so a
// relative base works on the Pi (<hostname>.local:8080), via a tunnel, or on a
// laptop. REACT_APP_API_BASE is only for running `npm start` against a backend
// on another host during development.
export const API_BASE_URL = process.env.REACT_APP_API_BASE || "/api";

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

  // Expo helper: which source produced the latest reading and how old it is.
  // { source: "pi"|"fake"|"replay"|null, age_s, ingested_at, stale_after_s, status, dry_run }
  async getDataSource() {
    const response = await axios.get(`${API_BASE_URL}/pidata/source`, { timeout: 4000 });
    return response.data;
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
