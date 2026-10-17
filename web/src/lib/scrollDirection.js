import { useEffect, useRef, useState } from 'react';

const TOP = 80;
const MOVE = 8;
const IDLE_MS = 1200;

// Pure core: should floating buttons be shown after this scroll sample?
export function nextVisibility(prev, { y, lastY, now, lastMoveAt }) {
  if (y < TOP) return true;
  const delta = y - lastY;
  if (delta >= MOVE) return false;
  if (-delta >= MOVE) return true;
  if (now - lastMoveAt >= IDLE_MS) return true;
  return prev;
}

// Hook: true while floating buttons should show. Hides on scroll down, shows on scroll up or after idle.
export function useScrollDirection() {
  const [visible, setVisible] = useState(true);
  const state = useRef({ lastY: 0, lastMoveAt: 0, visible: true, timer: null });

  useEffect(() => {
    const s = state.current;
    s.lastY = window.scrollY || 0;
    s.lastMoveAt = Date.now();

    const apply = (next) => {
      if (next !== s.visible) {
        s.visible = next;
        setVisible(next);
      }
    };
    const onScroll = () => {
      const now = Date.now();
      const y = window.scrollY || 0;
      const next = nextVisibility(s.visible, { y, lastY: s.lastY, now, lastMoveAt: s.lastMoveAt });
      if (y !== s.lastY) {
        s.lastMoveAt = now;
      }
      s.lastY = y;
      apply(next);
      clearTimeout(s.timer);
      s.timer = setTimeout(() => apply(true), IDLE_MS + 50);
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      clearTimeout(s.timer);
    };
  }, []);

  return visible;
}
