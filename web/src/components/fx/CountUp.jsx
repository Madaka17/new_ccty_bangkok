// A number that runs up to its value when it first shows, and glides to each new value after that. Anything that
// is not a plain number (a dash, text) is shown as it is. Still for "reduce motion".
import { useEffect, useRef, useState } from 'react';
import { animate, useReducedMotion } from 'framer-motion';

export default function CountUp({ value, duration = 1.1, format = (n) => Math.round(n).toLocaleString('th-TH') }) {
  const target = typeof value === 'number' && Number.isFinite(value) ? value : null;
  const still = useReducedMotion();
  const [shown, setShown] = useState(still || target == null ? target : 0);
  const from = useRef(still ? target : 0);
  useEffect(() => {
    if (target == null) return undefined;
    if (still) {
      setShown(target);
      return undefined;
    }
    const controls = animate(from.current ?? 0, target, {
      duration, ease: [0.16, 1, 0.3, 1], onUpdate: (v) => setShown(v),
    });
    from.current = target;
    return () => controls.stop();
  }, [target, still, duration]);
  return target == null ? value : format(shown);
}
