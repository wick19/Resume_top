import { useEffect, useState } from "react";

export default function SlidingNumber({
  value,
  from,
  delay = 0,
}: {
  value: number | null;
  from?: number;
  delay?: number;
}) {
  const [shown, setShown] = useState(from ?? value ?? 0);

  useEffect(() => {
    if (value == null) return;
    const origin = shown;
    const to = value;
    if (origin === to) return;
    const duration = 420;
    const startAt = performance.now() + delay;
    let frame = 0;
    const tick = (now: number) => {
      if (now < startAt) {
        frame = requestAnimationFrame(tick);
        return;
      }
      const t = Math.min(1, (now - startAt) / duration);
      const eased = 1 - (1 - t) ** 3;
      setShown(Math.round(origin + (to - origin) * eased));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // shown is the animation origin; including it would restart every frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, delay]);

  return <span className="tabular-nums">{value == null ? "—" : shown}</span>;
}
