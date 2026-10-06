import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

export type FieldPoint = { x: number; y: number };

export type FieldBox = { left: number; top: number; right: number; bottom: number };

export type TailorFieldHandle = {
  fire: (source: HTMLElement, sheet: HTMLElement) => void;
};

type Side = "left" | "right" | "top" | "bottom";

type Plan = {
  side: Side;
  along: number;
  lane: number;
  delay: number;
  bend: number;
  extra: boolean;
  spread: number;
};

type Lock = {
  plans: Plan[];
  origin: FieldPoint;
  sheet: HTMLElement;
  started: number;
};

const DURATION = 1560;
const PRIMARY = "0, 64, 240";
const ACCENT = "0, 160, 240";

function rgba(rgb: string, alpha: number) {
  return `rgba(${rgb}, ${alpha})`;
}

function clamp(value: number, min: number, max: number) {
  if (min > max) return max;
  return Math.min(max, Math.max(min, value));
}

function unit(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function polyLength(pts: FieldPoint[]) {
  let total = 0;
  for (let i = 1; i < pts.length; i += 1) {
    total += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  }
  return total;
}

function clip(pts: FieldPoint[], distance: number): FieldPoint[] {
  if (pts.length === 0) return [];
  const out: FieldPoint[] = [pts[0]];
  let remain = Math.max(0, distance);
  for (let i = 1; i < pts.length; i += 1) {
    const a = pts[i - 1];
    const b = pts[i];
    const seg = Math.hypot(b.x - a.x, b.y - a.y);
    if (seg < 0.001) continue;
    if (remain >= seg) {
      out.push(b);
      remain -= seg;
      continue;
    }
    const t = remain / seg;
    out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
    break;
  }
  return out;
}

function measure(el: HTMLElement, root: HTMLElement): FieldBox | null {
  const box = el.getBoundingClientRect();
  const base = root.getBoundingClientRect();
  if (box.width < 8 || box.height < 8) return null;
  return {
    left: box.left - base.left,
    top: box.top - base.top,
    right: box.right - base.left,
    bottom: box.bottom - base.top,
  };
}

function exitPoint(source: FieldBox, sheet: FieldBox): FieldPoint {
  const cx = (source.left + source.right) / 2;
  const cy = (source.top + source.bottom) / 2;
  if (source.right <= sheet.left + 6) return { x: source.right + 2, y: cy };
  if (source.left >= sheet.right - 6) return { x: source.left - 2, y: cy };
  if (source.bottom <= sheet.top + 6) return { x: cx, y: source.bottom + 2 };
  if (source.top >= sheet.bottom - 6) return { x: cx, y: source.top - 2 };
  return { x: source.right + 2, y: cy };
}

function buildPlans(seed: number): Plan[] {
  const sides: Side[] = ["left", "bottom", "top", "right"];
  const plans: Plan[] = [];
  sides.forEach((side, group) => {
    for (let lane = 0; lane < 3; lane += 1) {
      const n = group * 3 + lane;
      const along = clamp(0.2 + lane * 0.3 + (unit(seed + n * 3.7) - 0.5) * 0.1, 0.12, 0.88);
      const baseDelay = side === "left" ? 0 : side === "bottom" ? 0.08 : side === "top" ? 0.14 : 0.22;
      plans.push({
        side,
        along,
        lane,
        delay: baseDelay + lane * 0.045,
        bend: 0.26 + unit(seed + n * 2.3) * 0.42,
        extra: unit(seed + n * 5.1) > 0.5,
        spread: 0.18 + lane * 0.28 + (unit(seed + n) - 0.5) * 0.08,
      });
    }
  });
  return plans;
}

function pin(sheet: FieldBox, side: Side, along: number): FieldPoint {
  const kiss = 3;
  const t = clamp(along, 0.1, 0.9);
  if (side === "left") return { x: sheet.left - kiss, y: sheet.top + t * (sheet.bottom - sheet.top) };
  if (side === "right") return { x: sheet.right + kiss, y: sheet.top + t * (sheet.bottom - sheet.top) };
  if (side === "top") return { x: sheet.left + t * (sheet.right - sheet.left), y: sheet.top - kiss };
  return { x: sheet.left + t * (sheet.right - sheet.left), y: sheet.bottom + kiss };
}

function route(from: FieldPoint, end: FieldPoint, plan: Plan, sheet: FieldBox, bounds: { w: number; h: number }): FieldPoint[] {
  const pts: FieldPoint[] = [];
  const add = (x: number, y: number) => {
    const last = pts[pts.length - 1];
    if (last && Math.hypot(last.x - x, last.y - y) < 1) return;
    pts.push({ x, y });
  };
  const nudge = (plan.spread - 0.45) * 6;

  if (plan.side === "left") {
    const leftX = clamp(sheet.left - 18 - plan.lane * 22 + nudge, from.x + 8, sheet.left - 8);
    const midX = clamp(leftX + (plan.bend - 0.5) * 8, from.x + 8, sheet.left - 8);
    const yb = from.y + (end.y - from.y) * plan.bend;
    add(from.x, from.y);
    add(leftX, from.y);
    add(leftX, yb);
    add(midX, yb);
    add(midX, end.y);
    add(end.x, end.y);
    return pts;
  }

  const band = plan.side === "bottom" ? 0 : plan.side === "right" ? 1 : 2;
  const column = band * 3 + plan.lane;
  const yOpen = clamp(sheet.bottom + 36 + band * 108 + plan.lane * 28 + nudge, sheet.bottom + 18, bounds.h - 14);
  const xOpen = clamp(sheet.left + 36 + column * 32, sheet.left + 20, Math.min(sheet.right - 28, bounds.w - 20));

  add(from.x, from.y);
  if (from.y > sheet.bottom + 6) {
    const mouth = sheet.left + 18;
    const fanY = clamp(from.y + (column - 4) * 18, sheet.bottom + 20, bounds.h - 14);
    add(mouth, from.y);
    add(mouth, fanY);
    add(xOpen, fanY);
    add(xOpen, yOpen);
  } else {
    const dropX = clamp(from.x + 10 + column * 8, from.x + 6, sheet.left - 8);
    add(dropX, from.y);
    add(dropX, yOpen);
    add(xOpen, yOpen);
  }

  if (plan.side === "bottom") {
    const jogY = clamp(yOpen + (plan.extra ? 14 : 8), sheet.bottom + 16, bounds.h - 12);
    const xb = xOpen + (end.x - xOpen) * plan.bend;
    add(xb, yOpen);
    add(xb, jogY);
    add(end.x, jogY);
    add(end.x, end.y);
    return pts;
  }

  const rightX = clamp(
    sheet.right + (plan.side === "top" ? 108 : 26) + plan.lane * 30 + nudge,
    sheet.right + 14,
    bounds.w - 12,
  );
  add(rightX, yOpen);

  if (plan.side === "right") {
    const yb = yOpen + (end.y - yOpen) * plan.bend;
    const midX = clamp(rightX + (plan.extra ? 16 : 0), sheet.right + 14, bounds.w - 12);
    add(rightX, yb);
    add(midX, yb);
    add(midX, end.y);
    add(end.x, end.y);
    return pts;
  }

  const topY = clamp(sheet.top - 16 - plan.lane * 18, 8, sheet.top - 6);
  const xb = rightX + (end.x - rightX) * plan.bend;
  add(rightX, topY);
  add(xb, topY);
  add(xb, clamp(topY - 8, 6, sheet.top - 6));
  add(end.x, clamp(topY - 8, 6, sheet.top - 6));
  add(end.x, end.y);
  return pts;
}

function ease(t: number) {
  const x = clamp(t, 0, 1);
  return 1 - (1 - x) ** 3;
}

const TailorField = forwardRef<TailorFieldHandle>(function TailorField(_, ref) {
  const rootRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const lockRef = useRef<Lock | null>(null);
  const rafRef = useRef<number | null>(null);
  const reduceRef = useRef(false);

  useImperativeHandle(ref, () => ({
    fire(source, sheet) {
      if (reduceRef.current) return;
      const root = rootRef.current;
      if (!root) return;
      const sourceBox = measure(source, root);
      const sheetBox = measure(sheet, root);
      if (!sourceBox || !sheetBox) return;
      lockRef.current = {
        plans: buildPlans(Math.random() * 1000),
        origin: exitPoint(sourceBox, sheetBox),
        sheet,
        started: performance.now(),
      };
    },
  }));

  useEffect(() => {
    const field = rootRef.current;
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d") ?? null;
    if (!field || !canvas || !context) return;
    const node: HTMLDivElement = field;
    const board: HTMLCanvasElement = canvas;
    const ink: CanvasRenderingContext2D = context;
    reduceRef.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let alive = true;

    function resize() {
      const story = node.parentElement;
      if (story) {
        const storyBox = story.getBoundingClientRect();
        const width = document.documentElement.clientWidth;
        node.style.left = `${-storyBox.left}px`;
        node.style.width = `${width}px`;
        node.style.right = "auto";
      }
      const box = node.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      board.width = Math.max(1, Math.floor(box.width * dpr));
      board.height = Math.max(1, Math.floor(box.height * dpr));
      ink.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    const observer = new ResizeObserver(resize);
    observer.observe(node);
    window.addEventListener("resize", resize);
    resize();

    function stroke(points: FieldPoint[], color: string, width: number, cap: CanvasLineCap = "square") {
      if (points.length < 2) return;
      ink.beginPath();
      points.forEach((p, i) => {
        if (i === 0) ink.moveTo(p.x, p.y);
        else ink.lineTo(p.x, p.y);
      });
      ink.strokeStyle = color;
      ink.lineWidth = width;
      ink.lineJoin = "miter";
      ink.miterLimit = 2;
      ink.lineCap = cap;
      ink.stroke();
    }

    function tail(points: FieldPoint[], span: number): FieldPoint[] {
      if (points.length < 2) return points;
      const gathered: FieldPoint[] = [points[points.length - 1]];
      let remain = span;
      for (let i = points.length - 1; i > 0; i -= 1) {
        const b = points[i];
        const a = points[i - 1];
        const seg = Math.hypot(b.x - a.x, b.y - a.y) || 1;
        if (remain >= seg) {
          gathered.push(a);
          remain -= seg;
          continue;
        }
        const t = remain / seg;
        gathered.push({ x: b.x + (a.x - b.x) * t, y: b.y + (a.y - b.y) * t });
        break;
      }
      return gathered.reverse();
    }

    function frame(now: number) {
      if (!alive) return;
      ink.clearRect(0, 0, node.clientWidth, node.clientHeight);
      const lock = lockRef.current;
      if (lock) {
        const t = (now - lock.started) / DURATION;
        if (t >= 1) {
          lock.sheet.classList.remove("is-receiving");
          lockRef.current = null;
        } else {
          lock.sheet.classList.toggle("is-receiving", t > 0.4 && t < 0.94);
          const sheet = measure(lock.sheet, node);
          const fade = t < 0.72 ? 1 : 1 - (t - 0.72) / 0.28;
          const drawT = Math.min(1, t / 0.62);
          const flicker = 0.84 + 0.16 * Math.sin(now / 48);
          const bounds = { w: node.clientWidth, h: node.clientHeight };

          if (sheet) {
            const traces = lock.plans.map((plan) => {
              const pts = route(lock.origin, pin(sheet, plan.side, plan.along), plan, sheet, bounds);
              return { plan, pts, length: Math.max(1, polyLength(pts)) };
            });

            traces.forEach((trace) => {
              const local = (drawT - trace.plan.delay) / (1 - trace.plan.delay);
              const progress = ease(local);
              if (progress <= 0) return;
              const drawn = clip(trace.pts, progress * trace.length);
              stroke(drawn, rgba(PRIMARY, 0.42 * fade * flicker), 1.15);
              stroke(drawn, rgba(ACCENT, 0.28 * fade), 0.45);

              if (progress < 0.985) {
                const head = drawn[drawn.length - 1];
                ink.save();
                ink.shadowColor = rgba(ACCENT, 0.8 * fade);
                ink.shadowBlur = 14;
                stroke(tail(drawn, 92), rgba(ACCENT, 0.28 * fade), 2, "round");
                stroke(tail(drawn, 46), rgba(ACCENT, 0.62 * fade), 2.4, "round");
                stroke(tail(drawn, 16), rgba(ACCENT, fade), 3, "round");
                ink.beginPath();
                ink.arc(head.x, head.y, 3.1, 0, Math.PI * 2);
                ink.fillStyle = rgba(ACCENT, fade);
                ink.fill();
                ink.restore();
              }
            });

            traces.forEach((trace) => {
              const local = (drawT - trace.plan.delay) / (1 - trace.plan.delay);
              const progress = ease(local);
              if (progress <= 0) return;
              const travel = progress * trace.length;
              let walked = 0;
              for (let i = 1; i < trace.pts.length - 1; i += 1) {
                const prevSpan = Math.hypot(trace.pts[i].x - trace.pts[i - 1].x, trace.pts[i].y - trace.pts[i - 1].y);
                const nextSpan = Math.hypot(trace.pts[i + 1].x - trace.pts[i].x, trace.pts[i + 1].y - trace.pts[i].y);
                walked += prevSpan;
                if (walked > travel - 1) break;
                if (prevSpan < 6 || nextSpan < 6) continue;
                const joint = trace.pts[i];
                ink.beginPath();
                ink.arc(joint.x, joint.y, 1.8, 0, Math.PI * 2);
                ink.fillStyle = rgba(ACCENT, 0.95 * fade);
                ink.fill();
              }

              if (progress >= 0.985) {
                const end = trace.pts[trace.pts.length - 1];
                const ringT = clamp((t - 0.5 - trace.plan.delay * 0.2) / 0.22, 0, 1);
                ink.save();
                ink.shadowColor = rgba(ACCENT, 0.75 * fade);
                ink.shadowBlur = 14;
                ink.beginPath();
                ink.arc(end.x, end.y, 3.3, 0, Math.PI * 2);
                ink.fillStyle = rgba(PRIMARY, fade);
                ink.fill();
                ink.beginPath();
                ink.arc(end.x, end.y, 1.4, 0, Math.PI * 2);
                ink.fillStyle = rgba(ACCENT, fade);
                ink.fill();
                ink.restore();
                if (ringT > 0 && ringT < 1) {
                  ink.beginPath();
                  ink.arc(end.x, end.y, 4 + ringT * 11, 0, Math.PI * 2);
                  ink.strokeStyle = rgba(ACCENT, (1 - ringT) * fade);
                  ink.lineWidth = 1.25;
                  ink.stroke();
                }
              }
            });
          }

          ink.beginPath();
          ink.arc(lock.origin.x, lock.origin.y, 2.2, 0, Math.PI * 2);
          ink.fillStyle = rgba(PRIMARY, 0.9 * fade);
          ink.fill();
        }
      }
      rafRef.current = requestAnimationFrame(frame);
    }

    rafRef.current = requestAnimationFrame(frame);
    return () => {
      alive = false;
      lockRef.current?.sheet.classList.remove("is-receiving");
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", resize);
      observer.disconnect();
    };
  }, []);

  return (
    <div ref={rootRef} className="home-field" aria-hidden="true">
      <canvas ref={canvasRef} className="home-field-canvas" />
    </div>
  );
});

export default TailorField;
