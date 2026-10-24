import PageShell from "@/components/PageShell";
import G85Dashboard from "@/components/strategy/G85Dashboard";

export default function Page() {
  return (
    <PageShell title="85g 策略" subtitle="拆解當沖交易員 85g 的公開對帳單：熱門族群股開高時開盤先賣、收盤前買回，吃「開高走低」；指數大跌開低時反手做多。附明日觀察名單、近期訊號與 5 年回測。" badge="Intraday Fade">
      <G85Dashboard />
      <p className="mt-10 text-[11px] leading-relaxed text-[#7c8aa0]">
        資料來源：IG @85ga_stock 公開貼文（對帳單截圖、文字）；證交所／櫃買中心每日行情、暫停先賣後買註記；回測使用 Yahoo Finance 日線與 5 分 K。本頁為策略研究，不代表原作者的實際下單邏輯，也不構成任何投資建議。
      </p>
    </PageShell>
  );
}
