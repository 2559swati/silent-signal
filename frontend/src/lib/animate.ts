import { useEffect, useRef, useState } from 'react';

/** Cap for stagger delays so long lists never feel slow. */
export function staggerDelay(index: number, stepMs = 45, maxMs = 320): string {
  return `${Math.min(index * stepMs, maxMs)}ms`;
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

/**
 * Animate a real backend-provided number from 0 to its target.
 * Never invents values: the endpoint is always the supplied target.
 * Jumps straight to the target under reduced motion or on remount races.
 */
export function useCountUp(target: number, durationMs = 750): number {
  const [display, setDisplay] = useState(0);
  const raf = useRef(0);
  const shownFor = useRef<number | null>(null);

  useEffect(() => {
    if (shownFor.current === target) return;
    if (prefersReducedMotion() || durationMs <= 0) {
      shownFor.current = target;
      setDisplay(target);
      return;
    }
    shownFor.current = target;
    const start = performance.now();
    const tick = (now: number): void => {
      const t = Math.min(1, (now - start) / durationMs);
      // easeOutCubic: fast start, gentle landing.
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(target * eased);
      if (t < 1) {
        raf.current = requestAnimationFrame(tick);
      } else {
        setDisplay(target);
      }
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, durationMs]);

  return display;
}
