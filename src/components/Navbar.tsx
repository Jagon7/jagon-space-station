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
      { label: "氣氛評估", href: "/atmosphere",  badge: "16:45" },
      { label: "漲停訊號", href: "/limit-up" },
      { label: "隔日追蹤", href: "/next-day" },
      { label: "統計戰報", href: "/stats" },
      { label: "族群強弱", href: "/sectors" },
    ],
  },
  {
    label: "基礎情報",
    children: [
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
      { label: "券差偵測", href: "/short",       badge: "20:08" },
      { label: "處置預警",      href: "/disposition",  badge: "19:00" },
      { label: "ETF 成分股動態", href: "/etf-flow",     badge: "22:30" },
    ],
  },
  { label: "情報截收", href: "/announcements" },
];

function DropdownMenu({ items }: { items: MenuItem[] }) {
  return (
    <div className="absolute top-full left-0 mt-1 w-44 bg-[#0d1220] border border-[#1e2a3a] rounded-lg shadow-xl overflow-hidden z-50">
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className="flex items-center justify-between px-4 py-2.5 text-sm text-slate-300 hover:bg-[#1e2a3a] hover:text-[#00d4aa] transition-colors"
        >
          <span>{item.label}</span>
          {item.badge && (
            <span className="text-xs text-slate-500 font-mono">{item.badge}</span>
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
    <nav className="sticky top-0 z-50 border-b border-[#1e2a3a] bg-[#080c1a]/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14" ref={navRef}>

          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-7 h-7 rounded-lg bg-[#00d4aa]/10 border border-[#00d4aa]/30 flex items-center justify-center group-hover:bg-[#00d4aa]/20 transition-colors">
              <Satellite className="w-4 h-4 text-[#00d4aa]" />
            </div>
            <div className="flex flex-col leading-none">
              <span className="font-bold text-white text-sm tracking-widest uppercase">Jagon</span>
              <span className="text-[9px] text-[#00d4aa]/70 tracking-[0.2em] uppercase font-mono">Space Station</span>
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
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[#22c55e]/20 bg-[#22c55e]/5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
              <span className="text-[11px] text-[#22c55e] font-mono tracking-wide">訊號接收中</span>
            </div>
          </div>

          {/* Mobile */}
          <button className="md:hidden p-2 text-slate-400 hover:text-white" onClick={() => setMobileOpen(!mobileOpen)}>
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div className="md:hidden border-t border-[#1e2a3a] bg-[#0d1220]">
          {navItems.map((item) => (
            <div key={item.label}>
              {item.href ? (
                <Link href={item.href} className="block px-4 py-3 text-sm text-slate-300 hover:text-[#00d4aa] border-b border-[#1e2a3a]/50" onClick={() => setMobileOpen(false)}>
                  {item.label}
                </Link>
              ) : (
                <>
                  <div className="px-4 py-2 text-[10px] text-slate-500 uppercase tracking-widest border-b border-[#1e2a3a]/50 font-mono">{item.label}</div>
                  {item.children?.map((child) => (
                    <Link key={child.href} href={child.href} className="flex items-center justify-between px-6 py-2.5 text-sm text-slate-400 hover:text-[#00d4aa] border-b border-[#1e2a3a]/30" onClick={() => setMobileOpen(false)}>
                      <span>{child.label}</span>
                      {child.badge && <span className="text-xs text-slate-600 font-mono">{child.badge}</span>}
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
