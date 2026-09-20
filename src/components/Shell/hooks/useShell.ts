import { useEffect, useState } from 'react';
import { api } from '../../../services/api';
import type { KnowledgeBase } from '../../../types';

export function useShell() {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [online, setOnline] = useState(false);
  useEffect(() => {
    let active = true;
    const load = () => api.kbs().then(data => { if (active) { setKbs(data); setOnline(true); } }).catch(() => { if (active) setOnline(false); });
    load();
    const timer = setInterval(load, 10000);
    window.addEventListener('knowledge-changed', load);
    return () => { active = false; clearInterval(timer); window.removeEventListener('knowledge-changed', load); };
  }, []);
  return { kbs, online };
}
