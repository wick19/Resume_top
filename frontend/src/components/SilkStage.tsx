import { Component, type ReactNode } from "react";
import Silk from "./Silk";

class SilkFrame extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return <div className="h-full w-full bg-gradient-to-br from-[#d5e4ff] via-bg to-[#c9dcff]" />;
    }
    return this.props.children;
  }
}

export function SilkBand() {
  return (
    <SilkFrame>
      <Silk
        speed={1.15}
        scale={0.72}
        color="#0040f0"
        noiseIntensity={0.8}
        rotation={0.55}
        lightMode
        ribbon
        lift
        highlight="#00a0f0"
      />
    </SilkFrame>
  );
}

export default function SilkStage({ ribbon = false }: { ribbon?: boolean }) {
  return (
    <SilkFrame>
      <Silk
        speed={ribbon ? 1.5 : 2.4}
        scale={ribbon ? 1.05 : 1.15}
        color="#0040f0"
        noiseIntensity={ribbon ? 1.15 : 0.7}
        rotation={ribbon ? 0.08 : 0.2}
        lightMode
        ribbon={ribbon}
        highlight="#00a0f0"
      />
    </SilkFrame>
  );
}
