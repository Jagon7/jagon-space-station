"use client";

import { useCallback, useEffect, useState } from "react";

const KEY = "watchlist";
const EVT = "watchlist-change";

function readList(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

/** 自選股清單（只存在這台瀏覽器），各頁共用、即時同步 */
export function useWatchlist() {
  const [list, setList] = useState<string[]>([]);
  useEffect(() => {
    const sync = () => setList(readList());
    sync();
    window.addEventListener(EVT, sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener(EVT, sync); window.removeEventListener("storage", sync); };
  }, []);
  const save = useCallback((next: string[]) => {
    try { localStorage.setItem(KEY, JSON.stringify([...new Set(next)])); } catch {}
    window.dispatchEvent(new Event(EVT));
  }, []);
  const has = useCallback((c: string) => list.includes(c), [list]);
  const toggle = useCallback((c: string) => save(list.includes(c) ? list.filter((x) => x !== c) : [...list, c]), [list, save]);
  return { list, has, toggle, save };
}
