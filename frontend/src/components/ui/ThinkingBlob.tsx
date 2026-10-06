export type ThinkingStatus =
  | "thinking"
  | "matching"
  | "scoring"
  | "rewriting"
  | "generating"
  | "paused"
  | "complete";

/** Uneven rays. Lengths and angles stay off a regular star on purpose. */
const RAYS = [
  { angle: -18, len: 40, thick: 11 },
  { angle: 22, len: 30, thick: 9 },
  { angle: 54, len: 37, thick: 10 },
  { angle: 92, len: 26, thick: 8.5 },
  { angle: 128, len: 38, thick: 10.5 },
  { angle: 166, len: 28, thick: 8 },
  { angle: 204, len: 36, thick: 10 },
  { angle: 246, len: 24, thick: 8 },
  { angle: 282, len: 39, thick: 11 },
  { angle: 326, len: 31, thick: 9 },
];

type StatusDynamics = {
  bodyScale: string;
  bodyDur: string;
  bodyRot?: string;
  rotDur?: string;
  armScale: string;
  armDur: string;
  lightPath: string;
  lightDur: string;
  coreColor: string;
  glowColor: string;
  hubR: number;
};

const DYNAMICS: Record<ThinkingStatus, StatusDynamics> = {
  thinking: {
    bodyScale: "1;0.74;1.06;1",
    bodyDur: "2.4s",
    armScale: "1;0.88;1.05;1",
    armDur: "3.2s",
    lightPath: "-3 -2;3 1;1 3;-3 -2",
    lightDur: "3.6s",
    coreColor: "#F7FBFF",
    glowColor: "#00A0F0",
    hubR: 12,
  },
  matching: {
    bodyScale: "1;0.65;1.12;0.92;1",
    bodyDur: "1.45s",
    bodyRot: "0;12;-8;0",
    rotDur: "3.2s",
    armScale: "1;0.78;1.14;1",
    armDur: "2.2s",
    lightPath: "-4 -1;4 -2;2 4;-4 -1",
    lightDur: "2.2s",
    coreColor: "#EAF2FF",
    glowColor: "#00E5FF",
    hubR: 12.5,
  },
  scoring: {
    bodyScale: "1;0.52;1.2;1",
    bodyDur: "1.05s",
    bodyRot: "0;-6;8;-3;0",
    rotDur: "1.8s",
    armScale: "1;0.7;1.22;1",
    armDur: "1.6s",
    lightPath: "-2 -3;3 -1;0 4;-2 -3",
    lightDur: "1.5s",
    coreColor: "#FFFFFF",
    glowColor: "#00F0FF",
    hubR: 13.5,
  },
  rewriting: {
    bodyScale: "1;0.68;1.15;0.95;1",
    bodyDur: "1.7s",
    bodyRot: "0;24;-18;0",
    rotDur: "4.4s",
    armScale: "1;0.82;1.18;1",
    armDur: "2.6s",
    lightPath: "-5 -3;3 -4;5 2;-2 4;-5 -3",
    lightDur: "3.0s",
    coreColor: "#E0F2FE",
    glowColor: "#38BDF8",
    hubR: 12,
  },
  generating: {
    bodyScale: "1;0.58;1.14;1",
    bodyDur: "0.82s",
    armScale: "1;0.75;1.12;1",
    armDur: "1.2s",
    lightPath: "-1 -1;2 0;0 2;-1 -1",
    lightDur: "0.9s",
    coreColor: "#FFFFFF",
    glowColor: "#67E8F9",
    hubR: 13,
  },
  paused: {
    bodyScale: "1;0.92;1.02;1",
    bodyDur: "8s",
    armScale: "1;0.96;1.02;1",
    armDur: "10s",
    lightPath: "0 0;1 1;0 0",
    lightDur: "12s",
    coreColor: "#CBD5E1",
    glowColor: "#64748B",
    hubR: 11,
  },
  complete: {
    bodyScale: "1",
    bodyDur: "0s",
    armScale: "1",
    armDur: "0s",
    lightPath: "0 0",
    lightDur: "0s",
    coreColor: "#F7FBFF",
    glowColor: "#00A0F0",
    hubR: 12,
  },
};

export default function ThinkingBlob({
  status = "thinking",
  size = 48,
  className = "",
  title,
}: {
  status?: ThinkingStatus;
  size?: number;
  className?: string;
  title?: string;
}) {
  const d = DYNAMICS[status];
  const reduced =
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const quiet = status === "complete" || reduced;

  return (
    <span
      className={`relative inline-flex items-center justify-center transition-transform hover:scale-105 ${className}`}
      style={{ width: size, height: size, display: "inline-flex", flex: "none", verticalAlign: "middle" }}
      aria-label={title || `ThinkingBlob • ${status.toUpperCase()} mode`}
    >
      <svg viewBox="0 0 100 100" width={size} height={size}>
        <title>{title || `ThinkingBlob [${status.toUpperCase()}] • Atelier Sartorial Engine`}</title>
        <g transform="translate(50 50)">
          <g>
            {!quiet && (
              <animateTransform
                attributeName="transform"
                type="scale"
                values={d.bodyScale}
                dur={d.bodyDur}
                repeatCount="indefinite"
                calcMode="spline"
                keySplines="0.45 0.05 0.55 1;0.4 0 0.2 1;0.45 0.05 0.55 1"
              />
            )}
            {d.bodyRot && !quiet && (
              <animateTransform
                attributeName="transform"
                type="rotate"
                values={d.bodyRot}
                dur={d.rotDur}
                repeatCount="indefinite"
                additive="sum"
                calcMode="spline"
                keySplines="0.4 0 0.6 1;0.4 0 0.6 1;0.4 0 0.6 1"
              />
            )}
            {RAYS.map((ray, index) => {
              const odd = index % 2 === 1;
              const rayDelay = odd ? index * 0.14 : index * 0.18;
              const rayFill = status === "matching" && odd ? "#0066FF" : "#0040F0";
              return (
                <g key={ray.angle} transform={`rotate(${ray.angle})`}>
                  <g>
                    {!quiet && (
                      <animateTransform
                        attributeName="transform"
                        type="scale"
                        values={d.armScale}
                        dur={d.armDur}
                        begin={`${rayDelay}s`}
                        repeatCount="indefinite"
                        calcMode="spline"
                        keySplines="0.45 0.05 0.55 1;0.45 0.05 0.55 1;0.45 0.05 0.55 1"
                      />
                    )}
                    <ellipse cx="0" cy={-ray.len / 2} rx={ray.thick / 2} ry={ray.len / 2} fill={rayFill} />
                  </g>
                </g>
              );
            })}
            <circle r={d.hubR} fill="#0040F0" />
            <g>
              {!quiet && (
                <animateTransform
                  attributeName="transform"
                  type="translate"
                  values={d.lightPath}
                  dur={d.lightDur}
                  repeatCount="indefinite"
                  calcMode="spline"
                  keySplines="0.4 0 0.6 1;0.4 0 0.6 1;0.4 0 0.6 1"
                />
              )}
              <circle r={status === "scoring" ? 4 : 3.2} fill={d.glowColor} />
              <circle r={status === "scoring" ? 2 : 1.5} cx="-0.5" cy="-0.5" fill={d.coreColor} />
            </g>
          </g>
        </g>
      </svg>
    </span>
  );
}
