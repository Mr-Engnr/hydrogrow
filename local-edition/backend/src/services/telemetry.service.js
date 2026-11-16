const db = require("../db/db");

// Matches the blob filter the old /pidata used before picking the newest name.
const BLOB_RE = /^\d{8}_\d{6}_\d+\.json$/;

/**
 * Rebuild the JSON document the Azure Function stored as a blob:
 * the raw Pi payload with "timestamp" overwritten by the ingest time
 * The Pi's own value stays available as pi_timestamp.
 */
function blobDocument(row) {
  const data = JSON.parse(row.raw_json);
  data.timestamp = row.ingested_at;
  return data;
}

/** Latest reading = greatest blob_name among names matching the regex, like the old listBlobsFlat loop. */
function latest() {
  const row = db.get().prepare(
    "SELECT * FROM telemetry WHERE blob_name GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]_*.json' " +
    "ORDER BY blob_name DESC LIMIT 1"
  ).get();
  if (!row || !BLOB_RE.test(row.blob_name)) return null;
  return { row, data: blobDocument(row) };
}

/** Verbatim port of pidata.routes.js's remap. */
function remapForDashboard(data) {
  return {
    ph: data.pH ?? data.ph ?? null,
    ec: data.ec,
    waterTemp: data.temperature,
    humidity: data.humidity,
    waterLevel: data.waterLevel ?? data.water_level ?? null,
    waterLevelPct: data.water_level_pct ?? null,
    waterLow: data.water_low ?? null,
    health_status: data.nutrient_status?.label || data.nutrient_status || "Unknown",
    nutrient_confidence: data.nutrient_confidence,
    plant1: data.plant1 || null,
    plant2: data.plant2 || null,
    plant3: data.plant3 || null,
    disease_predictions: data.disease_predictions || null,
  };
}

/**
 * Port of the Azure Function `analytics`:
 *   cutoff = utcnow - days; include blobs whose YYYYMMDD (ingest date, midnight) >= cutoff
 *   bucket by that date; average pH/EC/temp/humidity; labels come from the pH buckets only.
 * Ruling 1: pH is read from the normalised column (accepts "pH" and "ph").
 */
function analytics(days) {
  const cutoff = new Date(Date.now() - days * 86400000);
  // ingest_day is YYYY-MM-DD at UTC midnight; compare as a date like the Function did.
  const cutoffDay = cutoff.toISOString().slice(0, 10);
  const rows = db.get().prepare(
    "SELECT ingest_day, ph, ec, temperature, humidity, raw_json FROM telemetry " +
    "WHERE ingest_day >= ? ORDER BY blob_name"
  ).all(cutoffDay);

  const daily = { ph: {}, ec: {}, temp: {}, humidity: {} };
  const push = (bucket, day, v) => { (bucket[day] ||= []).push(v); };
  for (const r of rows) {
    // The Function appended whatever value the key held (including null, which
    // would then poison sum()). Columns here are null when the key was absent
    // OR null; the keys that can be null in a real Pi frame are temperature and
    // humidity, which it also only appended when present. Skipping nulls is the
    // closest faithful behaviour that does not NaN the average.
    const d = r.ingest_day;
    if (r.ph !== null) push(daily.ph, d, r.ph);
    if (r.ec !== null) push(daily.ec, d, r.ec);
    if (r.temperature !== null) push(daily.temp, d, r.temperature);
    if (r.humidity !== null) push(daily.humidity, d, r.humidity);
  }
  // Function: include if blob_date (that day's UTC midnight) >= cutoff (a datetime),
  // so the calendar day the cutoff falls on is excluded unless cutoff is exactly midnight.
  const include = (day) => Date.parse(day + "T00:00:00Z") >= cutoff.getTime();
  const labels = Object.keys(daily.ph).filter(include).sort();
  const avg = (lst) => (lst && lst.length ? Math.round((lst.reduce((a, b) => a + b, 0) / lst.length) * 100) / 100 : 0);
  const all = labels.flatMap((d) => daily.ph[d] || []);
  return {
    labels,
    daily_avg_ph: labels.map((d) => avg(daily.ph[d])),
    daily_avg_ec: labels.map((d) => avg(daily.ec[d])),
    daily_avg_temp: labels.map((d) => avg(daily.temp[d])),
    daily_avg_humidity: labels.map((d) => avg(daily.humidity[d])),
    overall_week_avg_ph: avg(all),
  };
}

/** Twin document in Azure Digital Twins shape. Returns null for unknown ids. */
function twin(twinId) {
  const d = db.get();
  const meta = d.prepare("SELECT model_id FROM twins WHERE twin_id = ?").get(twinId);
  if (!meta) return null;
  const props = d.prepare("SELECT property, value_json, updated_at FROM twin_state WHERE twin_id = ? ORDER BY property").all(twinId);
  let lastUpdate = null;
  const doc = { $dtId: twinId, $etag: null };
  const metadata = { $model: meta.model_id };
  for (const p of props) {
    doc[p.property] = JSON.parse(p.value_json);
    metadata[p.property] = { lastUpdateTime: p.updated_at + "Z" };
    if (!lastUpdate || p.updated_at > lastUpdate) lastUpdate = p.updated_at;
  }
  doc.$etag = `W/"${lastUpdate ? Buffer.from(lastUpdate).toString("base64url") : "empty"}"`;
  // Key order matters: $metadata goes LAST, as in ADT. Unity's WaterAlertSystem takes the first
  // `"waterlevel":` / `"ph":` / `"ec":` in the text; if $metadata came first it would hit
  // `"waterLevel":{"lastUpdateTime":...}` and parse 0.
  doc.$metadata = metadata;
  return doc;
}

function twinIds() {
  return db.get().prepare("SELECT twin_id FROM twins ORDER BY twin_id").all().map((r) => r.twin_id);
}

function ingestState() {
  const r = db.get().prepare("SELECT state_json, updated_at FROM service_state WHERE service = 'ingest'").get();
  return r ? { ...JSON.parse(r.state_json), updated_at: r.updated_at } : null;
}

function counts() {
  return db.get().prepare("SELECT COUNT(*) AS n, MIN(ingested_at) AS first, MAX(ingested_at) AS last FROM telemetry").get();
}

module.exports = { latest, remapForDashboard, analytics, twin, twinIds, ingestState, counts, blobDocument, BLOB_RE };
