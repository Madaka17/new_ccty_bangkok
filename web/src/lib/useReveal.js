// Scroll reveal: an element starts hidden and is shown once, the first time it scrolls into view. One shared
// IntersectionObserver serves every element (a Map of element -> callback). Without IntersectionObserver the
// element is shown at once, so content never stays hidden. The `rv-ready` class on <html> switches the hidden
// styles on (index.css), and it is only added where the observer exists.
import { useEffect, useRef, useState } from 'react';

const hasIO = () => typeof IntersectionObserver !== 'undefined';

// Pure decision: hidden at first only when the observer can reveal it later.
export function initialShown(ioAvailable = hasIO()) {
  return !ioAvailable;
}

const callbacks = new Map();
let observer = null;

function sharedObserver() {
  if (observer) return observer;
  observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const done = callbacks.get(entry.target);
      observer.unobserve(entry.target);
      callbacks.delete(entry.target);
      done?.();
    }
  }, { threshold: 0.15 });
  return observer;
}

if (hasIO() && typeof document !== 'undefined') {
  document.documentElement.classList.add('rv-ready');
}

export function useReveal() {
  const ref = useRef(null);
  const [shown, setShown] = useState(() => initialShown());
  useEffect(() => {
    const el = ref.current;
    if (shown || !el || !hasIO()) return undefined;
    callbacks.set(el, () => setShown(true));
    sharedObserver().observe(el);
    return () => {
      callbacks.delete(el);
      observer?.unobserve(el);
    };
  }, [shown]);
  return [ref, shown];
}
