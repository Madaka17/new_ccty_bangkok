import { FOCUS } from './dashboard/ui.jsx';
import NavIcon from './NavIcons.jsx';

// Segmented switch between the views of one page (Camera AI, Accidents & Risk): each view is a card,
// the open one lifts out of the tray. tabs: [{ id, label, icon }] (label only: no description line under it)
export default function ViewSwitch({ tabs, value, onChange, label }) {
  const cols = { 2: 'grid-cols-2', 3: 'grid-cols-1 md:grid-cols-3', 4: 'grid-cols-2 xl:grid-cols-4' }[tabs.length]
    || 'grid-cols-2 md:grid-cols-3 xl:grid-cols-5';
  return (
    <div role="tablist" aria-label={label} className={`seg-tray grid ${cols} gap-1.5 p-1.5 rounded-2xl w-full ${tabs.length > 2 ? '' : 'sm:w-fit sm:min-w-[520px]'}`}>
      {tabs.map((t) => {
        const on = value === t.id;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(t.id)}
            className={`cursor-pointer flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all duration-200 ${FOCUS} ${on ? 'seg-on' : 'seg-off'}`}
          >
            <span className={`shrink-0 grid place-items-center w-9 h-9 rounded-lg transition-colors duration-200 ${on ? 'bg-blue-600 text-white' : 'seg-icon'}`}>
              <NavIcon name={t.icon} className="w-5 h-5" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold truncate">{t.label}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
