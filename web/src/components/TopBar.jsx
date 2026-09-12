import { useState } from 'react';
import { motion } from 'framer-motion';
import { BellIcon, MapPinIcon, SparkleIcon, CameraIcon, StarIcon } from './Icons.jsx';
import { greetingByHour } from '../lib/store.js';

const NAV = [
  { id: 'dashboard', label: 'แดชบอร์ด', icon: StarIcon },
  { id: 'cameras', label: 'กล้อง', icon: CameraIcon },
  { id: 'map', label: 'แผนที่จราจร', icon: MapPinIcon },
  { id: 'yolo', label: 'AI ตรวจจับรถ', icon: CameraIcon },
  { id: 'ai', label: 'AI ผู้ช่วยการจราจร', icon: SparkleIcon },
];

export default function TopBar({ userName, onSaveName, liveCount, totalCount, aiActive, page, onNavigate }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(userName);

  const commit = () => {
    onSaveName(draft);
    setEditing(false);
  };

  return (
    <div className="px-4 pt-4 sm:px-6">
      <div className="glass rounded-[2rem] px-5 py-3 sm:px-8 flex flex-wrap items-center gap-3 sm:gap-4">
        {/* Greeting */}
        <div className="order-2 sm:order-1 flex-1 min-w-[180px]">
          <p className="text-sm text-ink-600">{greetingByHour()},</p>
          {editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                commit();
              }}
              className="flex items-center gap-2"
            >
              <label htmlFor="user-name" className="sr-only">ชื่อของคุณ</label>
              <input
                id="user-name"
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commit}
                maxLength={24}
                className="rounded-full bg-white/80 border border-lavender-200 px-3 py-1 text-base font-medium text-ink-900 w-40"
              />
            </form>
          ) : (
            <button
              type="button"
              onClick={() => {
                setDraft(userName);
                setEditing(true);
              }}
              title="แตะเพื่อเปลี่ยนชื่อ"
              className="cursor-pointer text-lg font-semibold text-ink-900 hover:text-lavender-700 transition-colors duration-200 rounded-full"
            >
              คุณ{userName}!
            </button>
          )}
        </div>

        {/* Centered logo */}
        <div className="order-1 sm:order-2 w-full sm:w-auto text-center">
          <h1 className="leading-tight">
            <span className="font-serif text-2xl sm:text-[1.75rem] font-semibold text-ink-900 tracking-tight">BKK Traffic</span>
            <span className="block sm:inline sm:ml-2 font-sans text-sm sm:text-base font-medium text-lavender-700">
              Your Street Smart Guide
            </span>
          </h1>
        </div>

        {/* Status + bell */}
        <div className="order-3 flex-1 flex items-center justify-end gap-2 sm:gap-3 min-w-[180px]">
          <div className="hidden sm:flex items-center gap-2 rounded-full bg-sage-50 border border-sage-100 px-3 py-1.5 text-sm text-sage-700">
            <span className="live-dot inline-block w-2.5 h-2.5 rounded-full bg-sage-400" aria-hidden="true" />
            {liveCount > 0 ? `กล้องเปิดอยู่ ${liveCount} ตัว` : `พร้อมใช้งาน ${totalCount} กล้อง`}
          </div>

          <motion.button
            type="button"
            onClick={() => onNavigate('ai')}
            whileTap={{ scale: 0.96 }}
            title="AI ผู้ช่วยการจราจร"
            aria-label="AI ผู้ช่วยการจราจร"
            className="cursor-pointer relative w-11 h-11 rounded-full bg-white/80 border border-cream-200 flex items-center justify-center hover:bg-gold-50 transition-colors duration-200"
          >
            <BellIcon />
            {aiActive && (
              <span className="absolute -top-0.5 -right-0.5 w-5 h-5 rounded-full bg-apricot-100 border-2 border-white flex items-center justify-center">
                <SparkleIcon className="w-3 h-3" />
              </span>
            )}
          </motion.button>
        </div>

        {/* Page nav */}
        <nav aria-label="หน้าหลัก" className="order-4 w-full flex justify-center">
          <div className="inline-flex flex-wrap justify-center gap-1 rounded-full bg-cream-100/80 p-1">
            {NAV.map((item) => {
              const on = page === item.id;
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onNavigate(item.id)}
                  aria-current={on ? 'page' : undefined}
                  className={`cursor-pointer relative inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition-colors duration-200 ${
                    on ? 'text-ink-900' : 'text-ink-600 hover:text-ink-900'
                  }`}
                >
                  {on && (
                    <motion.span
                      layoutId="nav-pill"
                      className="absolute inset-0 rounded-full bg-white shadow-soft"
                      transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                    />
                  )}
                  <span className="relative inline-flex items-center gap-1.5">
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </span>
                </button>
              );
            })}
          </div>
        </nav>
      </div>
    </div>
  );
}
