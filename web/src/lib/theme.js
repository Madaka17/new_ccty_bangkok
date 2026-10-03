import { useEffect, useState } from 'react';

// Light / dark switch. public/theme-init.js sets the `dark` class on <html> before the first paint (saved choice,
// else dark); this keeps the choice and tells open components when it changes.
const KEY = 'theme';
const root = () => document.documentElement;

export const currentTheme = () => (root().classList.contains('dark') ? 'dark' : 'light');

export function setTheme(t) {
  root().classList.toggle('dark', t === 'dark');
  root().style.colorScheme = t;
  try { localStorage.setItem(KEY, t); } catch {}
  window.dispatchEvent(new Event('themechange'));
}

export function useTheme() {
  const [theme, set] = useState(currentTheme);
  useEffect(() => {
    const on = () => set(currentTheme());
    window.addEventListener('themechange', on);
    return () => window.removeEventListener('themechange', on);
  }, []);
  return [theme, () => setTheme(theme === 'dark' ? 'light' : 'dark')];
}
