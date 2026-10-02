// Cameras where our AI flood watch sees water on the road (/api/flood/cameras), as camid -> label, in the camid
// form of /api/cameras/all (BMA cameras there are "BMA-<id>"). Read again every 5 minutes.
import { useEffect, useState } from 'react';
import { fetchFloodCameras } from '../../lib/api.js';

const LABEL = { severe: 'น้ำท่วมหนัก', flooded: 'น้ำท่วม', puddle: 'น้ำขัง' };

export default function useFlood() {
  const [flood, setFlood] = useState(() => new Map());
  useEffect(() => {
    const load = () => fetchFloodCameras().then((d) => {
      const m = new Map();
      for (const c of d.items || []) {
        if (LABEL[c.level] && !c.stale) m.set(c.kind === 'bma' ? `BMA-${c.camid}` : c.camid, LABEL[c.level]);
      }
      setFlood(m);
    }).catch(() => {});
    load();
    const id = setInterval(load, 5 * 60000);
    return () => clearInterval(id);
  }, []);
  return flood;
}
