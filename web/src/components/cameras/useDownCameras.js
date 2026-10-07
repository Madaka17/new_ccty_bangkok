// Cameras the newest status check could not pull from (/api/cameras/down, launch\camera_status.py every 5 minutes),
// as a Set of camid, for the live camera page to hide. Read again every 5 minutes, so a camera that comes back shows.
import { useEffect, useState } from 'react';
import { fetchDownCameras } from '../../lib/api.js';

export default function useDownCameras() {
  const [down, setDown] = useState(() => new Set());
  useEffect(() => {
    const load = () => fetchDownCameras().then((d) => setDown(new Set(d.items || []))).catch(() => {});
    load();
    const id = setInterval(load, 5 * 60000);
    return () => clearInterval(id);
  }, []);
  return down;
}
