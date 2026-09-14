import { useEffect, useRef } from 'react';
import { motion, useAnimationControls } from 'framer-motion';

export default function DataTile({ icon: Icon, label, value, tone }) {
 const controls = useAnimationControls();
 const prev = useRef(value);

 useEffect(() => {
 if (prev.current !== value) {
 prev.current = value;
 controls.start({ scale: [1, 1.06, 1], transition: { duration: 0.45, ease: 'easeOut' } });
    }
  }, [value, controls]);

 return (
    <motion.div animate={controls} className={`glass-strong rounded-xl px-5 py-4 flex items-center gap-4 ${tone}`}>
      <div className="w-12 h-12 rounded-lg bg-white flex items-center justify-center shrink-0">
        <Icon className="w-7 h-7" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-ink-600">{label}</p>
        <p className="font-serif text-3xl font-semibold text-ink-900 leading-none mt-0.5 tabular-nums">{value}</p>
      </div>
    </motion.div>
  );
}
