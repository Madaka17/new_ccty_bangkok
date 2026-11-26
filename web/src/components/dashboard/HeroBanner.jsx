// Photo hero for the overview page: one h1, a short subtitle and the primary action.
// The photo is decorative (alt=""); the overlay keeps white text above 4.5:1 contrast.
// On mount the photo settles from a slight zoom, and the title, subtitle and button float up in turn.
import { useEffect, useState } from 'react';
import Reveal from '../fx/Reveal.jsx';

export default function HeroBanner({ onPrimary, children }) {
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setSettled(true));   // after the first paint, so the zoom runs
    return () => cancelAnimationFrame(id);
  }, []);
  return (
    <section aria-labelledby="hero-title" className="hero-banner relative isolate overflow-hidden rounded-[var(--c-radius-card)] h-[220px] sm:h-[300px] lg:h-[360px]">
      <img
        src="/hero/benjakitti-1920.webp"
        srcSet="/hero/benjakitti-960.webp 960w, /hero/benjakitti-1920.webp 1920w"
        sizes="(min-width: 1024px) 1150px, 100vw"
        alt=""
        fetchpriority="high"
        decoding="async"
        className={`hero-img-settle ${settled ? 'in' : ''} absolute inset-0 -z-10 h-full w-full object-cover`}
      />
      <div aria-hidden="true" className="hero-overlay absolute inset-0 -z-10" />
      <div className="relative flex h-full flex-col items-center justify-center gap-4 px-5 pb-8 text-center">
        <Reveal as="h1" index={0} id="hero-title" className="font-serif-display text-balance text-3xl leading-tight font-normal text-white sm:text-5xl lg:text-6xl">
          เช็กกรุงเทพฯ ก่อนออกจากบ้าน
        </Reveal>
        <Reveal as="p" index={1} className="text-sm text-white/90 sm:text-base">รถติด น้ำท่วม อุบัติเหตุ อัปเดตสดทุกนาที</Reveal>
        <Reveal
          as="button"
          index={2}
          type="button"
          onClick={onPrimary}
          className="min-h-11 rounded-full border border-white/80 px-6 text-sm font-medium text-white transition-colors duration-200 hover:bg-white hover:text-[#052812] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
        >
          ดูสถานะตอนนี้
        </Reveal>
        {children}
      </div>
      <a
        href="https://commons.wikimedia.org/wiki/File:Benjakitti_Forest_Park_(I).jpg"
        target="_blank"
        rel="noopener noreferrer"
        className="absolute bottom-2 right-3 text-[11px] text-white/80 underline-offset-2 hover:underline"
      >
        ภาพ: Supanut Arunoprayote (CC BY 4.0)
      </a>
    </section>
  );
}
