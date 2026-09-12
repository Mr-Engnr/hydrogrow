import React, { useState, useEffect } from "react";
import { Line, Bar } from "react-chartjs-2";
import PlantStatusAlert from "../components/PlantStatusAlert";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from "chart.js";
import apiService from "../services/api.service";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

function getIssues(vals) {
  const { ph, ec, waterTemp, humidity, waterLevel, health_status } = vals;
  const critical = [];
  const warning = [];

  if (ph < 4.5 || ph > 7.5)
    critical.push({ severity: "critical", title: ph < 4.5 ? "pH critically low" : "pH critically high", action: ph < 4.5 ? "Add pH Up solution immediately — dangerously acidic for plants" : "Add pH Down solution immediately — dangerously alkaline for plants", reading: String(ph), target: "5.5 – 6.5" });
  else if (ph < 5.5 || ph > 6.5)
    warning.push({ severity: "warning", title: ph < 5.5 ? "pH slightly low" : "pH slightly high", action: "Adjust pH gradually using pH Up/Down solution", reading: String(ph), target: "5.5 – 6.5" });

  if (waterLevel <= 20)
    critical.push({ severity: "critical", title: "Water tank empty", action: "Refill reservoir before next cycle — pump will run dry", reading: `${waterLevel}%`, target: "> 40%" });
  else if (waterLevel <= 40)
    warning.push({ severity: "warning", title: "Water level low", action: "Top up reservoir soon to avoid pump damage", reading: `${waterLevel}%`, target: "> 40%" });

  if (ec < 1.0)
    critical.push({ severity: "critical", title: "EC critically low", action: "Add nutrient solution immediately — plants are starving", reading: String(ec), target: "1.5 – 2.5" });
  else if (ec > 3.0)
    critical.push({ severity: "critical", title: "EC critically high", action: "Dilute solution with fresh water — risk of nutrient burn", reading: String(ec), target: "1.5 – 2.5" });
  else if (ec < 1.5 || ec > 2.5)
    warning.push({ severity: "warning", title: ec < 1.5 ? "EC slightly low" : "EC slightly high", action: ec < 1.5 ? "Add a small dose of nutrients" : "Add fresh water to dilute slightly", reading: String(ec), target: "1.5 – 2.5" });

  if (waterTemp < 15 || waterTemp > 30)
    critical.push({ severity: "critical", title: waterTemp < 15 ? "Water too cold" : "Water too hot", action: "Adjust water temperature — risk of root damage and oxygen depletion", reading: `${waterTemp}°C`, target: "18 – 26°C" });
  else if (waterTemp < 18 || waterTemp > 26)
    warning.push({ severity: "warning", title: waterTemp < 18 ? "Water slightly cool" : "Water slightly warm", action: "Monitor and adjust water temperature gradually", reading: `${waterTemp}°C`, target: "18 – 26°C" });

  if (humidity < 40 || humidity > 80)
    critical.push({ severity: "critical", title: humidity < 40 ? "Humidity too low" : "Humidity too high", action: humidity < 40 ? "Increase humidity to prevent wilting" : "Reduce humidity to prevent mould and disease", reading: `${humidity}%`, target: "50 – 70%" });
  else if (humidity < 50 || humidity > 70)
    warning.push({ severity: "warning", title: "Humidity suboptimal", action: "Adjust humidity slightly for optimal growth", reading: `${humidity}%`, target: "50 – 70%" });

  const statusLabel = typeof health_status === "string"
    ? health_status
    : (health_status && typeof health_status.label === "string"
       ? health_status.label
       : "Unknown");
  if (statusLabel !== "Healthy" && statusLabel !== "Unknown") {
    const label = statusLabel.replace(/_/g, " ");
    warning.push({ severity: "warning", title: label, action: `Address ${label.toLowerCase()} after stabilising water and pH first`, reading: "Low", target: "ML prediction" });
  }

  return [...critical, ...warning];
}

function getOkReadings(vals) {
  const { ph, ec, waterTemp, humidity, waterLevel } = vals;
  const ok = [];
  if (ph >= 5.5 && ph <= 6.5) ok.push(`pH ${ph}`);
  if (ec >= 1.5 && ec <= 2.5) ok.push(`EC ${ec}`);
  if (waterTemp >= 18 && waterTemp <= 26) ok.push(`Temp ${waterTemp}°C`);
  if (humidity >= 50 && humidity <= 70) ok.push(`Humidity ${humidity}%`);
  if (waterLevel > 40) ok.push(`Water ${waterLevel}%`);
  return ok.length > 0 ? `${ok.join(" · ")} — all optimal` : "No readings currently optimal";
}

function getSensorStatus(name, value) {
  switch (name) {
    case "pH":
      return value >= 5.5 && value <= 6.5 ? "Optimal" : (value >= 4.5 && value <= 7.5 ? "Warning" : "Critical");
    case "EC":
      return value >= 1.5 && value <= 2.5 ? "Optimal" : (value >= 1.0 && value <= 3.0 ? "Warning" : "Critical");
    case "Water Temp (°C)":
      return value >= 18 && value <= 26 ? "Optimal" : (value >= 15 && value <= 30 ? "Warning" : "Critical");
    case "Humidity (%)":
      return value >= 50 && value <= 70 ? "Optimal" : (value >= 40 && value <= 80 ? "Warning" : "Critical");
    case "Water Level (%)":
      if (value === null) return "No data";
      return value > 40 ? "Optimal" : (value > 20 ? "Warning" : "Critical");
    default:
      return "Optimal";
  }
}

function getStatusColor(status) {
  switch (status) {
    case "Optimal": return "#198754";
    case "Warning": return "#ffc107";
    case "Critical": return "#dc3545";
    default: return "#6c757d";
  }
}

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("overview");
  const [sensorValues, setSensorValues] = useState({
    ph: 0,
    ec: 0,
    waterTemp: 0,
    humidity: 0,
    waterLevel: 0,
    waterLevelPct: null,
    health_status: "Unknown"
  });
  const [diseasePredictions, setDiseasePredictions] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [analyticsDays, setAnalyticsDays] = useState(7);

  // Live sensor data from Raspberry Pi
  useEffect(() => {
    const fetchData = async () => {
      try {
        const data = await apiService.getRaspberryPiData();
        
        if (Array.isArray(data) && data.length > 0) {
          const latest = data[data.length - 1];
          
          setSensorValues({
            ph: latest.ph || 0,
            ec: latest.ec || 0,
            waterTemp: latest.waterTemp || 0,
            humidity: latest.humidity || 0,
            waterLevel: latest.waterLevel || 0,
            waterLevelPct: latest.waterLevelPct ?? null,
            health_status: latest.health_status || "Unknown"
          });
          setDiseasePredictions(latest.disease_predictions || null);
        }
      } catch (err) {
        console.error("Error fetching Raspberry Pi data:", err);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000); 
    return () => clearInterval(interval);
  }, []);

  // Analytics data from Azure Function
  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const data = await apiService.getAnalytics(analyticsDays);
        setAnalyticsData(data);
      } catch (err) {
        console.error("Error fetching analytics data:", err);
      }
    };

    fetchAnalytics();
  }, [analyticsDays]);

  const lineData = {
    labels: ["8AM", "10AM", "12PM", "2PM", "4PM", "6PM"],
    datasets: [
      {
        label: "pH Level",
        data: Array(6).fill(sensorValues.ph),
        borderColor: "#198754",
        backgroundColor: "rgba(25,135,84,0.2)"
      },
      {
        label: "EC",
        data: Array(6).fill(sensorValues.ec),
        borderColor: "#fd7e14",
        backgroundColor: "rgba(253,126,20,0.2)"
      },
      {
        label: "Water Temp (°C)",
        data: Array(6).fill(sensorValues.waterTemp),
        borderColor: "#0dcaf0",
        backgroundColor: "rgba(13,202,240,0.2)"
      },
      {
        label: "Humidity (%)",
        data: Array(6).fill(sensorValues.humidity),
        borderColor: "#6f42c1",
        backgroundColor: "rgba(111,66,193,0.2)"
      }
    ]
  };

  const waterLevelData = {
    labels: ["Water Tank"],
    datasets: [{
      label: "Water Level (%)",
      data: [sensorValues.waterLevel],
      backgroundColor: "#0dcaf0"
    }]
  };

  const sensorGradients = [
    "linear-gradient(135deg, #198754, #0dcaf0)",
    "linear-gradient(135deg, #0d6b3d, #198754)",
    "linear-gradient(135deg, #28a745, #198754)",
    "linear-gradient(135deg, #0dcaf0, #0d6b3d)",
    "linear-gradient(135deg, #198754, #28a745)"
  ];

  return (
    <div style={{ backgroundColor: "#f8fdf7", minHeight: "100vh", paddingBottom: "50px" }}>
      <div className="container my-5">
        <div className="d-flex align-items-center mb-4">
          <img src={require('../assets/images/dwc_plant.jpg')} alt="DWC Plant" style={{ width: "80px", marginRight: "20px" }} />
          <h1 style={{ color: "#0d6b3d" }}>HydroGrow Smart Dashboard</h1>
        </div>

        <ul className="nav nav-tabs mb-4">
          <li className="nav-item">
            <button className={`nav-link ${activeTab === "overview" ? "active" : ""}`} onClick={() => setActiveTab("overview")} style={{ color: "#0d6b3d" }}>Overview</button>
          </li>
          <li className="nav-item">
            <button className={`nav-link ${activeTab === "analytics" ? "active" : ""}`} onClick={() => setActiveTab("analytics")} style={{ color: "#0d6b3d" }}>Analytics</button>
          </li>
        </ul>

        {activeTab === "overview" && (
          <>
            {/* Plant Health Status Banner */}
            <div className="mb-4">
              <PlantStatusAlert
                issues={getIssues(sensorValues)}
                okReadings={getOkReadings(sensorValues)}
                timestamp="Updated just now"
                plantName="DWC System"
              />
            </div>

            <div className="row g-4 mb-4">
              {[
                { name: "pH", value: sensorValues.ph },
                { name: "EC", value: sensorValues.ec },
                { name: "Water Temp (°C)", value: sensorValues.waterTemp },
                { name: "Humidity (%)", value: sensorValues.humidity },
                { name: "Water Level (%)", value: sensorValues.waterLevelPct }
              ].map((sensor, i) => {
                const status = getSensorStatus(sensor.name, sensor.value);
                const statusColor = getStatusColor(status);
                return (
                  <div key={i} className="col-md-2 col-sm-4 col-6">
                    <div
                      className="card text-center p-3 shadow-sm"
                      style={{
                        borderRadius: "15px",
                        background: sensorGradients[i],
                        color: "#fff",
                        border: "none"
                      }}
                    >
                      <h6>{sensor.name}</h6>
                      <h3>{sensor.value}</h3>
                      <span className="badge" style={{
                        backgroundColor: statusColor,
                        color: status === "Warning" ? "#000" : "#fff",
                        fontSize: "0.75rem"
                      }}>
                        {status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Plant Health Section */}
            <h5 className="mb-3" style={{ color: "#0d6b3d" }}>Plant Health</h5>
            <div className="row g-4 mb-4">
              {["plant1", "plant2", "plant3"].map((key, i) => {
                const plant = diseasePredictions ? diseasePredictions[key] : null;
                const label = plant ? plant.label : null;
                const confidence = plant ? plant.confidence : null;
                const isHealthy = label === "Healthy";
                const isDiseased = label && !isHealthy && confidence >= 0.7;
                const gradient = !plant
                  ? "linear-gradient(135deg, #6c757d, #adb5bd)"
                  : isHealthy
                    ? "linear-gradient(135deg, #198754, #28a745)"
                    : isDiseased
                      ? "linear-gradient(135deg, #dc3545, #c82333)"
                      : "linear-gradient(135deg, #ffc107, #fd7e14)";
                const statusText = !plant
                  ? ""
                  : isHealthy
                    ? "Healthy"
                    : isDiseased
                      ? "Disease Detected"
                      : "Uncertain";
                const badgeColor = !plant
                  ? "#6c757d"
                  : isHealthy
                    ? "#198754"
                    : isDiseased
                      ? "#dc3545"
                      : "#ffc107";
                const badgeTextColor = (!plant || statusText === "Uncertain") ? "#000" : "#fff";

                return (
                  <div key={key} className="col-md-4 col-sm-6 col-12">
                    <div
                      className="card text-center p-3 shadow-sm"
                      style={{
                        borderRadius: "15px",
                        background: gradient,
                        color: "#fff",
                        border: "none"
                      }}
                    >
                      <h6>Plant {i + 1}</h6>
                      {plant ? (
                        <>
                          <h3 style={{ fontSize: "1.2rem", marginBottom: "10px" }}>{label}</h3>
                          <div style={{
                            background: "rgba(255,255,255,0.3)",
                            borderRadius: "4px",
                            height: "6px",
                            marginBottom: "6px"
                          }}>
                            <div style={{
                              background: "#fff",
                              borderRadius: "4px",
                              height: "6px",
                              width: `${Math.round(confidence * 100)}%`
                            }} />
                          </div>
                          <small>{Math.round(confidence * 100)}% confidence</small>
                          <div className="mt-2">
                            <span className="badge" style={{
                              backgroundColor: badgeColor,
                              color: badgeTextColor,
                              fontSize: "0.75rem"
                            }}>
                              {statusText}
                            </span>
                          </div>
                        </>
                      ) : (
                        <p style={{ margin: "10px 0", opacity: 0.8 }}>No data yet</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="row g-4 mb-4">
              <div className="col-md-6">
                <div className="card p-3 shadow-sm" style={{height:"350px",borderRadius:"15px",border:"2px solid #198754"}}>
                  <h5 className="card-title mb-3" style={{color:"#0d6b3d"}}>Sensor Trends</h5>
                  <Line data={lineData} options={{maintainAspectRatio:false}} />
                </div>
              </div>

              <div className="col-md-6">
                <div className="card p-3 shadow-sm" style={{height:"350px",borderRadius:"15px",border:"2px solid #198754"}}>
                  <h5 className="card-title mb-3" style={{color:"#0d6b3d"}}>Water Level</h5>
                  <Bar data={waterLevelData} options={{ maintainAspectRatio:false, indexAxis:'y' }} />
                </div>
              </div>
            </div>
          </>
        )}

        {activeTab === "analytics" && (
          <div className="card p-4 shadow-sm" style={{borderRadius:"15px",border:"2px solid #198754"}}>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h5 className="card-title mb-0" style={{color:"#0d6b3d"}}>Sensor Trends</h5>
              <div className="btn-group" role="group">
                {[7, 14, 30].map((d) => (
                  <button
                    key={d}
                    type="button"
                    className={`btn btn-sm ${analyticsDays === d ? "btn-success" : "btn-outline-success"}`}
                    onClick={() => setAnalyticsDays(d)}
                  >
                    {d} Days
                  </button>
                ))}
              </div>
            </div>

            {analyticsData && analyticsData.labels ? (
              <>
                <div className="mb-3 text-muted" style={{fontSize:"0.9rem"}}>
                  Weekly Average pH: <strong>{analyticsData.overall_week_avg_ph ?? "N/A"}</strong>
                </div>
                <div className="row g-4">
                  {/* pH Chart */}
                  <div className="col-md-6">
                    <div className="card p-3 shadow-sm" style={{height:"300px",borderRadius:"15px",border:"1px solid #dee2e6"}}>
                      <h6 style={{color:"#198754"}}>pH Trend</h6>
                      <Line
                        data={{
                          labels: analyticsData.labels,
                          datasets: [{
                            label: "Avg pH",
                            data: analyticsData.daily_avg_ph,
                            borderColor: "#198754",
                            backgroundColor: "rgba(25,135,84,0.2)",
                            fill: true,
                            tension: 0.3
                          }]
                        }}
                        options={{ maintainAspectRatio: false, plugins: { legend: { display: false } } }}
                      />
                    </div>
                  </div>

                  {/* EC Chart */}
                  <div className="col-md-6">
                    <div className="card p-3 shadow-sm" style={{height:"300px",borderRadius:"15px",border:"1px solid #dee2e6"}}>
                      <h6 style={{color:"#fd7e14"}}>EC Trend</h6>
                      <Line
                        data={{
                          labels: analyticsData.labels,
                          datasets: [{
                            label: "Avg EC",
                            data: analyticsData.daily_avg_ec,
                            borderColor: "#fd7e14",
                            backgroundColor: "rgba(253,126,20,0.2)",
                            fill: true,
                            tension: 0.3
                          }]
                        }}
                        options={{ maintainAspectRatio: false, plugins: { legend: { display: false } } }}
                      />
                    </div>
                  </div>

                  {/* Water Temperature Chart */}
                  <div className="col-md-6">
                    <div className="card p-3 shadow-sm" style={{height:"300px",borderRadius:"15px",border:"1px solid #dee2e6"}}>
                      <h6 style={{color:"#0dcaf0"}}>Water Temperature Trend</h6>
                      <Line
                        data={{
                          labels: analyticsData.labels,
                          datasets: [{
                            label: "Avg Temp (°C)",
                            data: analyticsData.daily_avg_temp,
                            borderColor: "#0dcaf0",
                            backgroundColor: "rgba(13,202,240,0.2)",
                            fill: true,
                            tension: 0.3
                          }]
                        }}
                        options={{ maintainAspectRatio: false, plugins: { legend: { display: false } } }}
                      />
                    </div>
                  </div>

                  {/* Humidity Chart */}
                  <div className="col-md-6">
                    <div className="card p-3 shadow-sm" style={{height:"300px",borderRadius:"15px",border:"1px solid #dee2e6"}}>
                      <h6 style={{color:"#6f42c1"}}>Humidity Trend</h6>
                      <Line
                        data={{
                          labels: analyticsData.labels,
                          datasets: [{
                            label: "Avg Humidity (%)",
                            data: analyticsData.daily_avg_humidity,
                            borderColor: "#6f42c1",
                            backgroundColor: "rgba(111,66,193,0.2)",
                            fill: true,
                            tension: 0.3
                          }]
                        }}
                        options={{ maintainAspectRatio: false, plugins: { legend: { display: false } } }}
                      />
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-muted">Loading analytics data…</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
