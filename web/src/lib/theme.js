import { useEffect, useState } from 'react';

// Light / dark switch. public/theme-init.js sets the `dark` class on <html> before the first paint (saved choice,
// else the device setting); this keeps the choice and tells open components when it changes. Until the viewer
// picks one, the page follows the device when it switches (e.g. dark at night).
const KEY = 'theme';
const root = () => document.documentElement;

export const currentTheme = () => (root().classList.contains('dark') ? 'dark' : 'light');

function apply(t) {
  root().classList.toggle('dark', t === 'dark');
  root().style.colorScheme = t;
  window.dispatchEvent(new Event('themechange'));
}

export function setTheme(t) {
  try { localStorage.setItem(KEY, t); } catch {}
  apply(t);
}

const savedTheme = () => {
  try { return localStorage.getItem(KEY); } catch { return null; }
};
window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', (e) => {
  if (!savedTheme()) apply(e.matches ? 'dark' : 'light');
});

export function useTheme() {
  const [theme, set] = useState(currentTheme);
  useEffect(() => {
    const on = () => set(currentTheme());
    window.addEventListener('themechange', on);
    return () => window.removeEventListener('themechange', on);
  }, []);
  return [theme, () => setTheme(theme === 'dark' ? 'light' : 'dark')];
}
