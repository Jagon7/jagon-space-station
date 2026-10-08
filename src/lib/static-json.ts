"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const cache = new Map<string, Promise<unknown>>();

/** 讀 public/data/ 底下建置時產生的 JSON；path 為 null 時不載入（例如分頁切到才抓）。 */
export function useStaticJson<T>(path: string | null): { data: T | null; error: boolean } {
  const [state, setState] = useState<{ path: string | null; data: T | null; error: boolean }>({ path: null, data: null, error: false });
  useEffect(() => {
    if (!path) return;
    let alive = true;
    if (!cache.has(path)) {
      cache.set(path, fetch(`${BASE}/data/${path}`, { cache: "no-cache" }).then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      }));
    }
    cache.get(path)!
      .then((d) => alive && setState({ path, data: d as T, error: false }))
      .catch(() => {
        cache.delete(path);
        if (alive) setState({ path, data: null, error: true });
      });
    return () => { alive = false; };
  }, [path]);
  // 切換 path 時不要回傳上一個 path 的資料
  return state.path === path ? { data: state.data, error: state.error } : { data: null, error: false };
}
