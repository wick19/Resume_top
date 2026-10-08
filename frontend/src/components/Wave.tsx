export default function Wave({ fill = "#f7f9fc" }: { fill?: string }) {
  return (
    <svg className="pointer-events-none block h-16 w-full sm:h-24" viewBox="0 0 1440 140" preserveAspectRatio="none" aria-hidden="true">
      <path
        fill={fill}
        opacity="0.5"
        d="M0,86 C240,16 460,124 740,58 C1020,0 1220,92 1440,34 L1440,140 L0,140 Z"
      />
      <path
        fill={fill}
        d="M0,24 C280,108 540,4 860,64 C1140,112 1300,18 1440,46 L1440,140 L0,140 Z"
      />
    </svg>
  );
}
