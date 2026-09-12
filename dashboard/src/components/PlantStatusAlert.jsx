import React from "react";

const pulseKeyframes = `
@keyframes plantAlertPulse {
  0%,100% { opacity: 1; }
  50%      { opacity: 0.25; }
}`;

const WarningTriangle = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 2L2 20h20L12 2z" stroke="#791F1F" strokeWidth="2" strokeLinejoin="round" fill="none"/>
    <line x1="12" y1="9" x2="12" y2="14" stroke="#791F1F" strokeWidth="2" strokeLinecap="round"/>
    <circle cx="12" cy="17.5" r="1.2" fill="#791F1F"/>
  </svg>
);

const ISSUE_STYLES = {
  critical: {
    rowBg:      "#fff",
    rowBorder:  "#F09595",
    dot:        "#E24B4A",
    title:      "#791F1F",
    action:     "#A32D2D",
    reading:    "#E24B4A",
    target:     "#A32D2D",
  },
  warning: {
    rowBg:      "#FAEEDA",
    rowBorder:  "#FAC775",
    dot:        "#BA7517",
    title:      "#412402",
    action:     "#633806",
    reading:    "#BA7517",
    target:     "#633806",
  },
};

const HEALTHY_ROW = {
  rowBg:    "#EAF3DE",
  rowBorder:"#97C459",
  dot:      "#639922",
  title:    "#173404",
  action:   "#3B6D11",
};

function IssueRow({ issue }) {
  const s = ISSUE_STYLES[issue.severity] || ISSUE_STYLES.warning;
  return (
    <div style={{
      display: "flex",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: "12px",
      backgroundColor: s.rowBg,
      border: `1px solid ${s.rowBorder}`,
      borderRadius: "8px",
      padding: "12px 14px",
    }}>
      {/* Left: dot + text */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: "10px", flex: 1 }}>
        <span style={{
          width: "10px", height: "10px", borderRadius: "50%",
          backgroundColor: s.dot, flexShrink: 0, marginTop: "3px",
        }} />
        <div>
          <div style={{ fontSize: "13.5px", fontWeight: 500, color: s.title, lineHeight: 1.3 }}>
            {issue.title}
          </div>
          <div style={{ fontSize: "12px", color: s.action, marginTop: "3px", lineHeight: 1.5 }}>
            {issue.action}
          </div>
        </div>
      </div>
      {/* Right: reading + target */}
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ fontSize: "13px", fontWeight: 500, color: s.reading }}>{issue.reading}</div>
        <div style={{ fontSize: "11px", color: s.target, marginTop: "2px" }}>{issue.target}</div>
      </div>
    </div>
  );
}

export default function PlantStatusAlert({ issues = [], okReadings = "", timestamp = "", plantName = "DWC System" }) {
  const criticalCount = issues.filter(i => i.severity === "critical").length;
  const hasIssues = issues.length > 0;

  const headerTitle = hasIssues
    ? `${criticalCount > 0 ? criticalCount : issues.length} ${criticalCount > 0 ? "Critical" : "Warning"} Issue${(criticalCount || issues.length) !== 1 ? "s" : ""} Detected`
    : "No Issues Detected";

  const headerSubtitle = hasIssues
    ? `${plantName} · Immediate action required`
    : `${plantName} · All systems nominal`;

  return (
    <>
      <style>{pulseKeyframes}</style>
      <div style={{
        width: "100%",
        borderRadius: "12px",
        border: "1px solid #F7C1C1",
        overflow: "hidden",
        fontFamily: "inherit",
      }}>

        {/* ── Section 1: Header ── */}
        <div style={{
          backgroundColor: "#F7C1C1",
          padding: "12px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
        }}>
          {/* Left: icon + text */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{
              width: "36px", height: "36px", borderRadius: "50%",
              backgroundColor: "#FCEBEB",
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <WarningTriangle />
            </div>
            <div>
              <div style={{ fontSize: "15px", fontWeight: 500, color: "#791F1F", lineHeight: 1.3 }}>
                {headerTitle}
              </div>
              <div style={{ fontSize: "12px", color: "#A32D2D", marginTop: "2px" }}>
                {headerSubtitle}
              </div>
            </div>
          </div>

          {/* Right: LIVE badge */}
          <div style={{
            display: "flex", alignItems: "center", gap: "6px",
            backgroundColor: "#E24B4A",
            borderRadius: "999px",
            padding: "4px 10px",
            flexShrink: 0,
          }}>
            <span style={{
              width: "7px", height: "7px", borderRadius: "50%",
              backgroundColor: "#FCEBEB",
              animation: "plantAlertPulse 1.8s ease-in-out infinite",
            }} />
            <span style={{
              fontSize: "11px", fontWeight: 700,
              color: "#FCEBEB", letterSpacing: "0.07em", textTransform: "uppercase",
            }}>
              Live
            </span>
          </div>
        </div>

        {/* ── Section 2: Body ── */}
        <div style={{
          backgroundColor: "#FCEBEB",
          padding: "14px 18px",
          display: "flex", flexDirection: "column", gap: "10px",
        }}>
          {hasIssues ? (
            issues.map((issue, i) => <IssueRow key={i} issue={issue} />)
          ) : (
            <div style={{
              display: "flex", alignItems: "center", gap: "10px",
              backgroundColor: HEALTHY_ROW.rowBg,
              border: `1px solid ${HEALTHY_ROW.rowBorder}`,
              borderRadius: "8px",
              padding: "12px 14px",
            }}>
              <span style={{
                width: "10px", height: "10px", borderRadius: "50%",
                backgroundColor: HEALTHY_ROW.dot, flexShrink: 0,
              }} />
              <span style={{ fontSize: "13.5px", fontWeight: 500, color: HEALTHY_ROW.title }}>
                All parameters optimal — system is healthy
              </span>
            </div>
          )}
        </div>

        {/* ── Section 3: Footer ── */}
        <div style={{
          backgroundColor: "#FCEBEB",
          borderTop: "1px solid #F7C1C1",
          padding: "10px 18px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{ fontSize: "11.5px", color: "#A32D2D" }}>{okReadings}</span>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{
              width: "6px", height: "6px", borderRadius: "50%",
              backgroundColor: "#639922",
              animation: "plantAlertPulse 1.8s ease-in-out infinite",
            }} />
            <span style={{ fontSize: "11px", color: "#A32D2D" }}>{timestamp}</span>
          </div>
        </div>

      </div>
    </>
  );
}
