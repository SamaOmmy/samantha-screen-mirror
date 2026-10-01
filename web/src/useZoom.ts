import { useEffect, useRef, useState, type RefObject } from "react";

const MAX_SCALE = 6;
const ONE = { scale: 1, x: 0, y: 0 };

/** Pinch (or wheel) to zoom, drag to pan, double-tap to reset, single tap = onTap. */
export function useZoom(stage: RefObject<HTMLDivElement | null>, onTap: () => void) {
  const [view, setView] = useState(ONE);
  const viewRef = useRef(view);
  viewRef.current = view;
  const tap = useRef(onTap);
  tap.current = onTap;

  useEffect(() => {
    const el = stage.current;
    if (!el) return;
    const pointers = new Map<number, { x: number; y: number }>();
    let startDist = 0, startScale = 1, moved = false, lastTap = 0;

    const apply = (v: typeof ONE) => {
      const scale = Math.min(MAX_SCALE, Math.max(1, v.scale));
      // Keep the picture from being dragged off-screen.
      const lx = ((scale - 1) * el.clientWidth) / 2, ly = ((scale - 1) * el.clientHeight) / 2;
      setView({ scale, x: Math.min(lx, Math.max(-lx, v.x)), y: Math.min(ly, Math.max(-ly, v.y)) });
    };
    const dist = () => {
      const [a, b] = [...pointers.values()];
      return Math.hypot(a.x - b.x, a.y - b.y);
    };

    const down = (e: PointerEvent) => {
      el.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 1) moved = false;
      if (pointers.size === 2) { startDist = dist(); startScale = viewRef.current.scale; moved = true; }
    };
    const move = (e: PointerEvent) => {
      const p = pointers.get(e.pointerId);
      if (!p) return;
      const dx = e.clientX - p.x, dy = e.clientY - p.y;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        apply({ ...viewRef.current, scale: (startScale * dist()) / startDist });
      } else if (viewRef.current.scale > 1) {
        if (Math.abs(dx) + Math.abs(dy) > 1) moved = true;
        apply({ ...viewRef.current, x: viewRef.current.x + dx, y: viewRef.current.y + dy });
      } else if (Math.hypot(dx, dy) > 4) {
        moved = true;
      }
    };
    const up = (e: PointerEvent) => {
      if (!pointers.delete(e.pointerId)) return;
      if (pointers.size > 0 || moved) return;
      const now = Date.now();
      if (now - lastTap < 300) {
        setView(ONE);
        lastTap = 0;
      } else {
        lastTap = now;
        window.setTimeout(() => { if (lastTap === now) tap.current(); }, 300);
      }
    };
    const cancel = (e: PointerEvent) => { pointers.delete(e.pointerId); };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      apply({ ...viewRef.current, scale: viewRef.current.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15) });
    };

    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", cancel);
    el.addEventListener("wheel", wheel, { passive: false });
    return () => {
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", cancel);
      el.removeEventListener("wheel", wheel);
    };
  }, [stage]);

  return { ...view, reset: () => setView(ONE) };
}
