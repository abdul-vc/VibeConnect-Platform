import React, { useState } from "react";

export interface TrendDataPoint {
  readonly label: string;
  readonly value: number;
}

export interface TelemetryTrendChartProps {
  readonly title: string;
  readonly subtitle?: string;
  readonly data: readonly TrendDataPoint[];
  readonly height?: number;
  readonly strokeColor?: string;
  readonly fillGradientId?: string;
  readonly valuePrefix?: string;
  readonly metricLabel?: string;
  readonly yAxisTicks?: readonly number[];
  readonly yMax?: number;
}

export const TelemetryTrendChart: React.FC<TelemetryTrendChartProps> = ({
  title,
  subtitle,
  data,
  height = 220,
  strokeColor = "#2563eb",
  fillGradientId = "trend-gradient",
  valuePrefix = "",
  metricLabel = "mrr",
  yAxisTicks = [60, 45, 30, 15, 0],
  yMax = 60,
}) => {
  const safeData: readonly TrendDataPoint[] =
    data && data.length > 0
      ? data
      : [
          { label: "Jan", value: 37.2 },
          { label: "Feb", value: 41.5 },
          { label: "Mar", value: 47.8 },
          { label: "Apr", value: 53.9 },
          { label: "May", value: 55.4 },
          { label: "Jun", value: 57.8 },
          { label: "Jul", value: 59.2 },
        ];

  // Dynamic hover index: null when not hovered so it never stays statically stuck
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const svgWidth = 640;
  const svgHeight = height;
  const paddingX = 40;
  const paddingTop = 25;
  const paddingBottom = 32;

  const chartWidth = svgWidth - paddingX * 2;
  const chartHeight = svgHeight - paddingTop - paddingBottom;

  const effectiveMax = yMax || Math.max(...safeData.map((d) => d.value), 10);
  const minVal = 0;

  const points = safeData.map((d, i) => {
    const x = paddingX + (i / Math.max(safeData.length - 1, 1)) * chartWidth;
    const y =
      paddingTop +
      chartHeight -
      ((d.value - minVal) / (effectiveMax - minVal)) * chartHeight;
    return { x, y, ...d };
  });

  // Smooth bezier curve calculation
  let pathD = "";
  if (points.length > 0) {
    pathD = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = i > 0 ? points[i - 1] : points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = i < points.length - 2 ? points[i + 2] : p2;

      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      pathD += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
    }
  }

  const areaD = pathD
    ? `${pathD} L ${points[points.length - 1].x} ${paddingTop + chartHeight} L ${points[0].x} ${paddingTop + chartHeight} Z`
    : "";

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const svgX = (mouseX / rect.width) * svgWidth;

    let closestIdx = 0;
    let minDiff = Infinity;
    points.forEach((pt, idx) => {
      const diff = Math.abs(pt.x - svgX);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = idx;
      }
    });
    setHoveredIndex(closestIdx);
  };

  const activePoint =
    hoveredIndex !== null && hoveredIndex >= 0 && hoveredIndex < points.length
      ? points[hoveredIndex]
      : null;

  return (
    <div
      style={{
        background: "var(--glass-surface-elevated, #ffffff)",
        border: "1px solid var(--border-glass, rgba(203, 213, 225, 0.95))",
        borderRadius: "14px",
        padding: "1.35rem 1.65rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.85rem",
        boxShadow: "var(--shadow-sm)",
        minWidth: 0,
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      <div>
        <h2
          style={{
            fontSize: "1.0625rem",
            fontWeight: 700,
            margin: 0,
            color: "var(--text-primary, #0f172a)",
          }}
        >
          {title}
        </h2>
        {subtitle && (
          <p
            style={{
              fontSize: "0.8125rem",
              color: "var(--text-secondary, #64748b)",
              margin: "0.2rem 0 0 0",
            }}
          >
            {subtitle}
          </p>
        )}
      </div>

      <div
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredIndex(null)}
        style={{
          width: "100%",
          height: `${svgHeight}px`,
          position: "relative",
          cursor: "crosshair",
        }}
      >
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          preserveAspectRatio="none"
          style={{ width: "100%", height: "100%", overflow: "visible" }}
        >
          <defs>
            <linearGradient id={fillGradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.18" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal dashed gridlines & Y-axis labels */}
          {yAxisTicks.map((val, idx) => {
            const y =
              paddingTop +
              chartHeight * (1 - (val - minVal) / (effectiveMax - minVal));
            return (
              <g key={idx}>
                <line
                  x1={paddingX}
                  y1={y}
                  x2={svgWidth - paddingX}
                  y2={y}
                  stroke="var(--border-subtle, rgba(203, 213, 225, 0.65))"
                  strokeDasharray="4 4"
                  strokeWidth="1"
                />
                <text
                  x={paddingX - 10}
                  y={y + 3.5}
                  textAnchor="end"
                  fontSize="11"
                  fill="var(--text-muted, #94a3b8)"
                  fontFamily="inherit"
                >
                  {val}
                </text>
              </g>
            );
          })}

          {/* Area fill */}
          {areaD && <path d={areaD} fill={`url(#${fillGradientId})`} />}

          {/* Line curve */}
          {pathD && (
            <path
              d={pathD}
              fill="none"
              stroke={strokeColor}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* X-axis labels */}
          {points.map((p, idx) => (
            <text
              key={idx}
              x={p.x}
              y={svgHeight - 10}
              textAnchor="middle"
              fontSize="11"
              fill={activePoint?.label === p.label ? "var(--brand-primary, #2563eb)" : "var(--text-muted, #64748b)"}
              fontFamily="inherit"
              fontWeight={activePoint?.label === p.label ? "700" : "500"}
              style={{ transition: "fill 0.15s ease, font-weight 0.15s ease" }}
            >
              {p.label}
            </text>
          ))}

          {/* Interactive vertical guideline and point circle with smooth transitions */}
          <line
            x1={activePoint ? activePoint.x : paddingX}
            y1={paddingTop}
            x2={activePoint ? activePoint.x : paddingX}
            y2={paddingTop + chartHeight}
            stroke="#3b82f6"
            strokeWidth="1.2"
            strokeDasharray="2 2"
            opacity={activePoint ? 0.6 : 0}
            style={{
              transition:
                "x1 0.16s cubic-bezier(0.16, 1, 0.3, 1), x2 0.16s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.18s ease",
            }}
          />
          <circle
            cx={activePoint ? activePoint.x : paddingX}
            cy={activePoint ? activePoint.y : paddingTop}
            r="7"
            fill="#3b82f6"
            fillOpacity={activePoint ? 0.25 : 0}
            style={{
              transition:
                "cx 0.16s cubic-bezier(0.16, 1, 0.3, 1), cy 0.16s cubic-bezier(0.16, 1, 0.3, 1), fill-opacity 0.18s ease",
            }}
          />
          <circle
            cx={activePoint ? activePoint.x : paddingX}
            cy={activePoint ? activePoint.y : paddingTop}
            r={activePoint ? 4 : 0}
            fill="#2563eb"
            stroke="#ffffff"
            strokeWidth="2"
            style={{
              transition:
                "cx 0.16s cubic-bezier(0.16, 1, 0.3, 1), cy 0.16s cubic-bezier(0.16, 1, 0.3, 1), r 0.18s cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          />
        </svg>

        {/* Floating tooltip card with smooth floating animation */}
        <div
          style={{
            position: "absolute",
            left: activePoint ? `${(activePoint.x / svgWidth) * 100}%` : "50%",
            top: activePoint ? `${((activePoint.y + 18) / svgHeight) * 100}%` : "50%",
            transform: activePoint
              ? "translate(-50%, 0) scale(1)"
              : "translate(-50%, -6px) scale(0.92)",
            opacity: activePoint ? 1 : 0,
            pointerEvents: "none",
            background: "var(--glass-surface-elevated, #ffffff)",
            border: "1px solid var(--border-subtle, #e2e8f0)",
            borderRadius: "8px",
            padding: "0.45rem 0.85rem",
            boxShadow: "0 4px 14px rgba(0, 0, 0, 0.08)",
            display: "flex",
            flexDirection: "column",
            gap: "0.15rem",
            minWidth: "72px",
            textAlign: "center",
            zIndex: 10,
            transition:
              "left 0.16s cubic-bezier(0.16, 1, 0.3, 1), top 0.16s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.18s ease, transform 0.18s cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        >
          <span
            style={{
              fontSize: "0.78125rem",
              fontWeight: 700,
              color: "var(--text-primary, #0f172a)",
            }}
          >
            {activePoint?.label || ""}
          </span>
          <span
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              color: "#2563eb",
            }}
          >
            {metricLabel} : {valuePrefix}{activePoint?.value || 0}
          </span>
        </div>
      </div>
    </div>
  );
};

export interface DonutSegment {
  readonly label: string;
  readonly value: number;
  readonly color: string;
}

export interface DonutDistributionChartProps {
  readonly title: string;
  readonly subtitle?: string;
  readonly segments: readonly DonutSegment[];
  readonly totalLabel?: string;
  readonly totalValue?: string | number;
}

export const DonutDistributionChart: React.FC<DonutDistributionChartProps> = ({
  title,
  subtitle,
  segments,
  totalLabel = "Total",
  totalValue,
}) => {
  const defaultSegments: readonly DonutSegment[] = [
    { label: "CRM", value: 24, color: "#2563eb" },
    { label: "Helpdesk", value: 19, color: "#0d9488" },
    { label: "HRMS", value: 16, color: "#f97316" },
    { label: "Asset Management", value: 14, color: "#ec4899" },
    { label: "Visitor Management", value: 12, color: "#ef4444" },
    { label: "Facility Management", value: 10, color: "#b91c1c" },
    { label: "Community App", value: 8, color: "#1d4ed8" },
    { label: "Event Platform", value: 6, color: "#10b981" },
    { label: "Inventory", value: 4, color: "#d97706" },
  ];

  const safeSegments =
    segments && segments.length > 0 ? segments : defaultSegments;

  // Active hover segment: null by default so the center shows totals cleanly when resting
  const [hoveredSegment, setHoveredSegment] = useState<DonutSegment | null>(null);

  const totalSum = safeSegments.reduce((acc, s) => acc + s.value, 0) || 1;
  const radius = 68;
  const circumference = 2 * Math.PI * radius;

  let currentOffset = 0;

  return (
    <div
      style={{
        background: "var(--glass-surface-elevated, #ffffff)",
        border: "1px solid var(--border-glass, rgba(203, 213, 225, 0.95))",
        borderRadius: "14px",
        padding: "1.35rem 1.65rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.85rem",
        boxShadow: "var(--shadow-sm)",
        minWidth: 0,
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      <div>
        <h2
          style={{
            fontSize: "1.0625rem",
            fontWeight: 700,
            margin: 0,
            color: "var(--text-primary, #0f172a)",
          }}
        >
          {title}
        </h2>
        {subtitle && (
          <p
            style={{
              fontSize: "0.8125rem",
              color: "var(--text-secondary, #64748b)",
              margin: "0.2rem 0 0 0",
            }}
          >
            {subtitle}
          </p>
        )}
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "1.1rem",
          flex: 1,
          justifyContent: "center",
        }}
      >
        {/* Donut ring container */}
        <div
          onMouseLeave={() => setHoveredSegment(null)}
          style={{
            position: "relative",
            width: "180px",
            height: "180px",
            flexShrink: 0,
          }}
        >
          <svg
            viewBox="0 0 180 180"
            style={{
              width: "100%",
              height: "100%",
              transform: "rotate(-90deg)",
              overflow: "visible",
            }}
          >
            {/* Background track ring */}
            <circle
              cx="90"
              cy="90"
              r={radius}
              fill="transparent"
              stroke="var(--border-subtle, rgba(203, 213, 225, 0.25))"
              strokeWidth="20"
            />
            {/* Segments */}
            {safeSegments.map((seg, idx) => {
              const segPct = seg.value / totalSum;
              const gap = 2;
              const arcLength = Math.max(segPct * circumference - gap, 1);
              const strokeDasharray = `${arcLength} ${circumference - arcLength}`;
              const strokeDashoffset = -currentOffset;
              currentOffset += segPct * circumference;

              const isCurrent = hoveredSegment?.label === seg.label;
              const isAnyHovered = hoveredSegment !== null;

              return (
                <circle
                  key={idx}
                  cx="90"
                  cy="90"
                  r={radius}
                  fill="transparent"
                  stroke={seg.color}
                  strokeWidth={isCurrent ? 25 : 20}
                  strokeDasharray={strokeDasharray}
                  strokeDashoffset={strokeDashoffset}
                  strokeLinecap="round"
                  onMouseEnter={() => setHoveredSegment(seg)}
                  style={{
                    cursor: "pointer",
                    transition:
                      "stroke-width 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.22s ease",
                    opacity: isCurrent ? 1 : isAnyHovered ? 0.65 : 0.95,
                  }}
                />
              );
            })}
          </svg>

          {/* Center Content: Totals when resting, interactive pill when hovered */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              pointerEvents: "none",
            }}
          >
            {/* Default Resting State: Platform totals */}
            <div
              style={{
                position: "absolute",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                opacity: hoveredSegment ? 0 : 1,
                transform: hoveredSegment ? "scale(0.88)" : "scale(1)",
                transition: "opacity 0.2s ease, transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
              }}
            >
              <span
                style={{
                  fontSize: "1.45rem",
                  fontWeight: 800,
                  color: "var(--text-primary, #0f172a)",
                  lineHeight: 1.1,
                }}
              >
                {totalValue !== undefined ? totalValue : totalSum}
              </span>
              <span
                style={{
                  fontSize: "0.6875rem",
                  color: "var(--text-muted, #94a3b8)",
                  textTransform: "uppercase",
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                }}
              >
                {totalLabel}
              </span>
            </div>

            {/* Hovered State: Compact card that fits within the donut hole without overflowing */}
            <div
              style={{
                position: "absolute",
                background: "var(--glass-surface-elevated, #ffffff)",
                border: "1px solid var(--border-subtle, #e2e8f0)",
                borderRadius: "8px",
                padding: "0.35rem 0.6rem",
                boxShadow: "0 4px 14px rgba(0, 0, 0, 0.09)",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "var(--text-primary, #0f172a)",
                maxWidth: "115px",
                textAlign: "center",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.25rem",
                zIndex: 2,
                opacity: hoveredSegment ? 1 : 0,
                transform: hoveredSegment ? "scale(1)" : "scale(0.85)",
                transition: "opacity 0.2s ease, transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
              }}
            >
              <span
                style={{
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  maxWidth: "80px",
                }}
                title={hoveredSegment?.label}
              >
                {hoveredSegment?.label || ""}
              </span>
              <span style={{ color: "var(--text-secondary, #64748b)" }}>:</span>
              <span style={{ color: hoveredSegment?.color || "#2563eb", fontWeight: 800 }}>
                {hoveredSegment?.value || 0}
              </span>
            </div>
          </div>
        </div>

        {/* Legend dots & labels with smooth hover highlights */}
        <div
          onMouseLeave={() => setHoveredSegment(null)}
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.45rem 0.95rem",
            justifyContent: "center",
            maxWidth: "380px",
          }}
        >
          {safeSegments.map((seg, idx) => {
            const isCurrent = hoveredSegment?.label === seg.label;
            const isAnyHovered = hoveredSegment !== null;

            return (
              <div
                key={idx}
                onMouseEnter={() => setHoveredSegment(seg)}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.35rem",
                  cursor: "pointer",
                  fontSize: "0.72rem",
                  fontWeight: isCurrent ? 700 : 500,
                  color: isCurrent
                    ? "var(--text-primary, #0f172a)"
                    : isAnyHovered
                    ? "var(--text-muted, #94a3b8)"
                    : seg.color,
                  transition: "color 0.16s ease, transform 0.16s ease, opacity 0.16s ease",
                  transform: isCurrent ? "scale(1.08)" : "scale(1)",
                  opacity: isCurrent ? 1 : isAnyHovered ? 0.6 : 1,
                }}
              >
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    backgroundColor: seg.color,
                    flexShrink: 0,
                    transition: "transform 0.16s ease",
                    transform: isCurrent ? "scale(1.25)" : "scale(1)",
                  }}
                />
                <span>{seg.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
