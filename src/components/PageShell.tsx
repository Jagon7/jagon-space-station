import Navbar from "./Navbar";
import Footer from "./Footer";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

type Props = {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
  badge?: string;
  back?: string;
};

export default function PageShell({ children, title, subtitle, badge, back = "/" }: Props) {
  return (
    <>
      <Navbar />
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Page header */}
        <div className="mb-8">
          <Link href={back} className="inline-flex items-center gap-1.5 text-xs text-[#8b97ab] hover:text-[#4f8cff] transition-colors mb-4 font-mono">
            <ArrowLeft className="w-3.5 h-3.5" /> 返回任務首頁
          </Link>
          <div className="flex items-end justify-between flex-wrap gap-3">
            <div>
              {badge && (
                <p className="text-[10px] font-mono text-[#7c8aa0] tracking-[0.25em] uppercase mb-1">{badge}</p>
              )}
              <h1 className="text-2xl font-bold text-white">{title}</h1>
              {subtitle && <p className="text-sm text-[#8b97ab] mt-1">{subtitle}</p>}
            </div>
          </div>
          <div className="mt-4 h-px bg-gradient-to-r from-[#4f8cff]/30 via-[#243247] to-transparent" />
        </div>
        {children}
      </main>
      <Footer />
    </>
  );
}
