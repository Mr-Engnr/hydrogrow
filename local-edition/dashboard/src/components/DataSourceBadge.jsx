import React from "react";

/**
 * Data-source badge + "last updated" indicator for the exhibition.
 *
 * The label is driven ONLY by the `source` of the latest stored reading
 * (GET /api/pidata/source), never by a config flag:
 *   "pi"      -> Live        (real firmware)
 *   "replay"  -> Demo Mode   (tools/replay.py, recorded readings)
 *   "fake"    -> Simulated   (tools/fake_pi.py, synthetic readings)
 *   anything else / no data / backend unreachable -> never "Live"
 *
 * "Last updated Xs ago" turns amber once the reading is older than
 * `staleAfterS` (backend sends 2 x SENSOR_INTERVAL_S).
 */

const SOURCE_STYLES = {
  pi:      { label: "Live",       bg: "#198754", fg: "#fff", dot: "#8fffb0" },
  replay:  { label: "Demo Mode",  bg: "#ffc107", fg: "#1a1a1a", dot: "#7a5200" },
  fake:    { label: "Simulated",  bg: "#0d6efd", fg: "#fff", dot: "#cfe2ff" },
  none:    { label: "No data",    bg: "#6c757d", fg: "#fff", dot: "#dee2e6" },
  unknown: { label: "Unknown source", bg: "#6c757d", fg: "#fff", dot: "#dee2e6" },
  offline: { label: "Backend unreachable", bg: "#dc3545", fg: "#fff", dot: "#f8d7da" },
};

export function describeSource(info, fetchFailed) {
  if (fetchFailed) return SOURCE_STYLES.offline;
  if (!info || !info.source) return SOURCE_STYLES.none;
  return SOURCE_STYLES[info.source] || SOURCE_STYLES.unknown;
}

export function formatAge(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "never";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s ago`;
  const h = Math.floor(s / 3600);
  return `${h}h ${Math.floor((s % 3600) / 60)}m ago`;
}

export default function DataSourceBadge({ info, ageS, fetchFailed = false }) {
  const style = describeSource(info, fetchFailed);
  const staleAfter = info?.stale_after_s ?? null;
  const stale = ageS != null && staleAfter != null && ageS > staleAfter;
  const isLive = !fetchFailed && info?.source === "pi";

  const pulse = `@keyframes dsbPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }`;

  return (
    <div className="d-flex align-items-center flex-wrap gap-2" data-testid="data-source-badge"
         title={info?.ingested_at ? `Stored at ${info.ingested_at} UTC` : ""}>
      <style>{pulse}</style>
      <span className="badge d-inline-flex align-items-center gap-2"
            data-source={fetchFailed ? "offline" : (info?.source || "none")}
            style={{ backgroundColor: style.bg, color: style.fg, fontSize: "0.85rem",
                     padding: "0.45em 0.8em", borderRadius: "999px", letterSpacing: "0.3px" }}>
        <span style={{ width: 9, height: 9, borderRadius: "50%", backgroundColor: style.dot,
                       display: "inline-block",
                       animation: isLive && !stale ? "dsbPulse 1.6s ease-in-out infinite" : "none" }} />
        {style.label}{isLive && stale ? " (stale)" : ""}
        {info?.dry_run ? " · pumps dry-run" : ""}
      </span>
      <span data-testid="last-updated" data-stale={stale ? "1" : "0"}
            style={{ fontSize: "0.85rem", fontWeight: stale ? 600 : 400,
                     color: fetchFailed ? "#dc3545" : stale ? "#b36b00" : "#6c757d" }}>
        {stale ? "⚠ " : ""}Last updated {formatAge(ageS)}
        {stale && staleAfter != null ? ` (no new data for over ${Math.round(staleAfter)}s)` : ""}
      </span>
    </div>
  );
}
