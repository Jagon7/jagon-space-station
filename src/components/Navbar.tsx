"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { ChevronDown, Satellite, Menu, X } from "lucide-react";

type MenuItem = { label: string; href: string; badge?: string };
type NavItem  = { label: string; href?: string; children?: MenuItem[] };

const navItems: NavItem[] = [
  { label: "任務首頁", href: "/" },
  {
    label: "即時戰情",
    children: [
      { label: "氣氛評估", href: "/atmosphere" },
      { label: "國際類股連動", href: "/global" },
      { label: "市場風險監控", href: "/risk" },
      { label: "漲停訊號", href: "/limit-up" },
      { label: "隔日追蹤", href: "/next-day" },
      { label: "成交排行", href: "/ranking" },
      { label: "技術選股", href: "/screener" },
      { label: "十日波段策略", href: "/strategy" },
      { label: "高週轉率黑K", href: "/turnover" },
      { label: "統計戰報", href: "/stats" },
      { label: "族群強弱", href: "/sectors" },
      { label: "產業細分類", href: "/industry" },
    ],
  },
  {
    label: "基礎情報",
    children: [
      { label: "券商報告", href: "/reports" },
      { label: "法說會", href: "/conferences" },
      { label: "CB 詢圈偵察", href: "/cb-watch" },
      { label: "自結盈餘", href: "/eps" },
      { label: "季報偵查", href: "/quarterly" },
      { label: "月營收", href: "/revenue" },
      { label: "庫藏股", href: "/buyback" },
      { label: "重大事件", href: "/events" },
    ],
  },
  {
    label: "籌碼雷達",
    children: [
      { label: "券差偵察", href: "/short" },
      { label: "處置預警",      href: "/disposition" },
      { label: "三大法人",       href: "/institutional" },
      { label: "期貨選擇權",     href: "/futures" },
      { label: "大戶持股",       href: "/holders" },
      { label: "分點買賣超",     href: "/broker" },
      { label: "內部人持股異動", href: "/insider" },
      { label: "ETF 持股",       href: "/etf-flow" },
    ],
  },
  { label: "情報截收", href: "/announcements" },
  { label: "自選股", href: "/watchlist" },
  { label: "個股查詢", href: "/search" },
  { label: "資料健檢", href: "/health" },
];

function DropdownMenu({ items }: { items: MenuItem[] }) {
  return (
    <div className="absolute top-full left-0 mt-1 w-44 bg-[#0d1220] border border-[#243247] rounded-lg shadow-xl overflow-hidden z-50">
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className="flex items-center justify-between px-4 py-2.5 text-sm text-slate-300 hover:bg-[#243247] hover:text-[#4f8cff] transition-colors"
        >
          <span>{item.label}</span>
          {item.badge && (
            <span className="text-xs text-[#8b97ab] font-mono">{item.badge}</span>
          )}
        </Link>
      ))}
    </div>
  );
}

export default function Navbar() {
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef<HTMLDivElement>(null);

  // 手機選單打開時鎖住背後頁面，滑動只捲選單本身
  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [mobileOpen]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenMenu(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <nav className="sticky top-0 z-50 border-b border-[#243247] bg-[#080c1a]/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14" ref={navRef}>

          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-7 h-7 rounded-lg bg-[#4f8cff]/10 border border-[#4f8cff]/30 flex items-center justify-center group-hover:bg-[#4f8cff]/20 transition-colors">
              <Satellite className="w-4 h-4 text-[#4f8cff]" />
            </div>
            <div className="flex flex-col leading-none">
              <span className="font-bold text-white text-sm tracking-widest uppercase">Jagon</span>
              <span className="text-[9px] text-[#4f8cff]/70 tracking-[0.2em] uppercase font-mono">Space Station</span>
            </div>
          </Link>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => (
              <div key={item.label} className="relative">
                {item.children ? (
                  <button
                    onClick={() => setOpenMenu(openMenu === item.label ? null : item.label)}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm text-slate-400 hover:text-white transition-colors rounded-md hover:bg-white/5"
                  >
                    {item.label}
                    <ChevronDown className={`w-3.5 h-3.5 transition-transform ${openMenu === item.label ? "rotate-180" : ""}`} />
                  </button>
                ) : (
                  <Link href={item.href!} className="px-3 py-1.5 text-sm text-slate-400 hover:text-white transition-colors rounded-md hover:bg-white/5 block">
                    {item.label}
                  </Link>
                )}
                {item.children && openMenu === item.label && <DropdownMenu items={item.children} />}
              </div>
            ))}
          </div>

          {/* Status badge */}
          <div className="hidden md:flex items-center gap-3">
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[#4f8cff]/20 bg-[#4f8cff]/5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#4f8cff] animate-pulse" />
              <span className="text-[11px] text-[#4f8cff] font-mono tracking-wide">訊號接收中</span>
            </div>
          </div>

          {/* Mobile */}
          <button className="md:hidden p-2 text-slate-400 hover:text-white" onClick={() => setMobileOpen(!mobileOpen)}>
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div className="md:hidden border-t border-[#243247] bg-[#0d1220] max-h-[calc(100dvh-3.5rem)] overflow-y-auto overscroll-contain pb-[env(safe-area-inset-bottom)]">
          {navItems.map((item) => (
            <div key={item.label}>
              {item.href ? (
                <Link href={item.href} className="block px-4 py-3 text-sm text-slate-300 hover:text-[#4f8cff] border-b border-[#243247]/50" onClick={() => setMobileOpen(false)}>
                  {item.label}
                </Link>
              ) : (
                <>
                  <div className="px-4 py-2 text-[10px] text-[#8b97ab] uppercase tracking-widest border-b border-[#243247]/50 font-mono">{item.label}</div>
                  {item.children?.map((child) => (
                    <Link key={child.href} href={child.href} className="flex items-center justify-between px-6 py-2.5 text-sm text-slate-400 hover:text-[#4f8cff] border-b border-[#243247]/30" onClick={() => setMobileOpen(false)}>
                      <span>{child.label}</span>
                      {child.badge && <span className="text-xs text-[#7c8aa0] font-mono">{child.badge}</span>}
                    </Link>
                  ))}
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </nav>
  );
}
