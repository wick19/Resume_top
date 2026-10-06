import { useRef, useState, type ReactNode } from "react";
import { motion, useMotionValue, useTransform, type PanInfo } from "motion/react";

function Draggable({
  enabled,
  onThrow,
  children,
}: {
  enabled: boolean;
  onThrow: () => void;
  children: ReactNode;
}) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotateX = useTransform(y, [-100, 100], [18, -18]);
  const rotateY = useTransform(x, [-100, 100], [-18, 18]);

  function onDragEnd(_event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) {
    if (Math.abs(info.offset.x) > 90 || Math.abs(info.offset.y) > 90) onThrow();
    else {
      x.set(0);
      y.set(0);
    }
  }

  if (!enabled) {
    return <div className="absolute inset-0">{children}</div>;
  }

  return (
    <motion.div
      className="absolute inset-0 cursor-grab active:cursor-grabbing"
      style={{ x, y, rotateX, rotateY }}
      drag
      dragConstraints={{ top: 0, right: 0, bottom: 0, left: 0 }}
      dragElastic={0.55}
      onDragEnd={onDragEnd}
    >
      {children}
    </motion.div>
  );
}

export default function GapDeck({ gaps, onOpen }: { gaps: string[]; onOpen: (label: string) => void }) {
  const depth = Math.min(4, gaps.length);
  const [deck, setDeck] = useState(() => Array.from({ length: depth }, (_, index) => index));
  const [seen, setSeen] = useState(1);
  const next = useRef(depth % Math.max(gaps.length, 1));

  function cycle() {
    setDeck((prev) => {
      if (prev.length < 2) return prev;
      const rest = prev.slice(0, -1);
      let incoming = next.current % gaps.length;
      if (gaps.length <= prev.length || rest.includes(incoming)) incoming = prev[prev.length - 1];
      else next.current = (next.current + 1) % gaps.length;
      return [incoming, ...rest];
    });
    setSeen((count) => (count >= gaps.length ? 1 : count + 1));
  }

  return (
    <div className="flex h-full flex-col">
      <p className="px-5 text-sm text-muted">
        {seen} of {gaps.length}. Drag the front card aside.
      </p>
      <div className="relative mx-auto mt-4 h-72 w-full max-w-md" style={{ perspective: 800 }}>
        {deck.map((gapIndex, index) => {
          const front = index === deck.length - 1;
          const label = gaps[gapIndex] || "";
          return (
            <Draggable key={gapIndex} enabled={front} onThrow={cycle}>
              <motion.div
                className="h-full w-full"
                animate={{
                  rotateZ: (deck.length - index - 1) * 3,
                  scale: 1 + index * 0.04 - deck.length * 0.04,
                  transformOrigin: "50% 100%",
                }}
                transition={{ type: "spring", stiffness: 260, damping: 24 }}
              >
                <article className="flex h-full flex-col justify-between rounded-2xl border border-ink/10 bg-white p-6 shadow-card">
                  <div>
                    <p className="text-[0.68rem] uppercase tracking-[0.14em] text-primary">Left off the PDF</p>
                    <p className="mt-3 text-[1.35rem] font-medium leading-snug tracking-[-0.02em]">{label}</p>
                  </div>
                  {front && (
                    <button
                      type="button"
                      className="btn self-start"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={() => onOpen(label)}
                    >
                      Open
                    </button>
                  )}
                </article>
              </motion.div>
            </Draggable>
          );
        })}
      </div>
    </div>
  );
}
