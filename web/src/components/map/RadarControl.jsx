import { Icon } from '../dashboard/icons.jsx';

// Rain radar button on the map's top-left corner: on/off, then the time of the shown frame, play and a scrubber.
// Looks like the map's other floating button (white pill) so it reads the same in light and dark.
export function RadarControl({ radar }) {
  const { showRainRadar, setShowRainRadar, radarTime, radarFrames, radarIndex, setRadarIndex, radarPlaying, setRadarPlaying, radarIsForecast, radarIsNow } = radar;
  const focus = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--c-primary)]';
  return (
    <div className="absolute left-3 top-3 z-10 flex max-w-[calc(100%-4.5rem)] flex-col items-start gap-2">
      <button
        type="button"
        onClick={() => setShowRainRadar(!showRainRadar)}
        aria-pressed={showRainRadar}
        className={`inline-flex items-center gap-1.5 h-11 min-w-11 px-3 rounded-full border text-sm font-semibold shadow-lg cursor-pointer transition-colors duration-200 ${focus} ${
          showRainRadar ? 'bg-[var(--c-sel-bg)] border-[var(--c-sel-bg)] text-[var(--c-sel-text)]' : 'bg-white border-slate-300 text-slate-900'
        }`}
      >
        <Icon name="rain" /> ฝน
      </button>
      {showRainRadar && radarFrames > 0 && (
        <div role="group" aria-label="ฝนย้อนหลัง" className="flex w-full max-w-72 items-center gap-2 rounded-full bg-white border border-slate-300 py-1 pl-1 pr-3 shadow-lg">
          <button
            type="button"
            onClick={() => setRadarPlaying(!radarPlaying)}
            aria-label={radarPlaying ? 'หยุด' : 'เล่นย้อนหลัง 2 ชม.'}
            className={`shrink-0 inline-flex h-11 w-11 items-center justify-center rounded-full bg-[var(--c-sel-bg)] text-[var(--c-sel-text)] cursor-pointer ${focus}`}
          >
            <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true">
              {radarPlaying ? <path d="M4 3h3v10H4zM9 3h3v10H9z" /> : <path d="M5 3l8 5-8 5z" />}
            </svg>
          </button>
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="text-xs font-semibold tabular-nums text-slate-900">{radarTime}</span>
            <span className="text-[10px] text-slate-600">{radarIsForecast ? 'คาดการณ์' : radarIsNow ? 'ตอนนี้' : 'ย้อนหลัง'}</span>
          </div>
          <input
            type="range"
            min="0"
            max={Math.max(0, radarFrames - 1)}
            step="1"
            value={radarIndex}
            onChange={(e) => {
              setRadarPlaying(false);
              setRadarIndex(Number(e.target.value));
            }}
            aria-label="เลือกเวลาฝน"
            aria-valuetext={radarTime ? `${radarTime}${radarIsForecast ? ' คาดการณ์' : radarIsNow ? ' ตอนนี้' : ' ย้อนหลัง'}` : undefined}
            className={`h-11 min-w-0 flex-1 cursor-pointer accent-blue-600 ${focus}`}
          />
        </div>
      )}
    </div>
  );
}
