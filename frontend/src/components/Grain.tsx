import { GrainGradient } from "@paper-design/shaders-react";

export default function Grain() {
  return (
    <div className="grain absolute inset-0">
      <GrainGradient
        width="100%"
        height="100%"
        colors={["#0040f0", "#00a0f0"]}
        colorBack="#eef3fb"
        softness={0.85}
        intensity={0.18}
        noise={0.22}
        shape="wave"
        speed={0.15}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}
