"""
推播訊息的共用排版：同一份內容同時產生
  - LINE Flex Message（卡片：深色標題列、分區、紅漲綠跌、底部按鈕）
  - 純文字版（Telegram／Discord，以及 LINE 的通知預覽 altText）
用法：
  m = Msg("📈 波段策略", "10/23 進場名單・10/22 收盤資料", accent="#4f8cff", url=f"{SITE}/strategy/", button="開啟策略頁")
  m.section("出量做多", "9 檔")
  m.stock("台郡", "6269", "收 78.7", "+27.5%", up=True, sub="放量Z 104.9・5/5 日放量")
  m.kv("外資", "+120億", up=True)
  m.note("進場：收盤前半小時")
  m.text() / m.flex()
"""
from __future__ import annotations

UP, DOWN, FLAT = "#E5484D", "#16A34A", "#64748B"  # 台股慣例：紅漲綠跌
INK, MUTED, LINE_C, HEAD_BG = "#0F172A", "#64748B", "#E2E8F0", "#0B1220"


def tone(up: bool | None) -> str:
    return FLAT if up is None else UP if up else DOWN


def sign_tone(v: float | None) -> str:
    return FLAT if not v else UP if v > 0 else DOWN


class Msg:
    def __init__(self, title: str, subtitle: str = "", accent: str = "#4f8cff", url: str | None = None, button: str = "開啟網站"):
        self.title, self.subtitle, self.accent, self.url, self.button = title, subtitle, accent, url, button
        self.items: list[tuple] = []

    # ---- 內容 ----
    def section(self, title: str, badge: str = ""):
        self.items.append(("section", title, badge))
        return self

    def kv(self, label: str, value: str, color: str | None = None, up: bool | None = None):
        self.items.append(("kv", label, value, color or (tone(up) if up is not None else INK)))
        return self

    def cols(self, mid: str = "", right: str = ""):
        """股票列表的欄位標題（例如「收盤」「週轉率」）"""
        self.items.append(("cols", mid, right))
        return self

    def stock(self, name: str, code: str, mid: str = "", right: str = "", up: bool | None = None, sub: str = "", color: str | None = None, star: bool = False):
        self.items.append(("stock", name, code, mid, right, color or tone(up), sub, star))
        return self

    def line(self, text: str, color: str = INK, bold: bool = False):
        self.items.append(("line", text, color, bold))
        return self

    def note(self, text: str):
        self.items.append(("note", text))
        return self

    def empty(self) -> bool:
        return not self.items

    # ---- 純文字 ----
    def text(self) -> str:
        out = [self.title + (f"｜{self.subtitle}" if self.subtitle else "")]
        for it in self.items:
            k = it[0]
            if k == "section":
                out += ["", f"【{it[1]}】{it[2]}"]
            elif k == "kv":
                out.append(f"{it[1]}：{it[2]}")
            elif k == "cols":
                continue
            elif k == "stock":
                _, name, code, mid, right, _, sub, star = it
                head = f"{'⭐' if star else '・'}{name} {code}" + (f" {mid}" if mid else "") + (f"｜{right}" if right else "")
                out.append(head)
                if sub:
                    out += [f"   {x}" for x in sub.split("\n")]
            elif k == "line":
                out.append(it[1])
            elif k == "note":
                out.append(f"※ {it[1]}")
        if self.url:
            out += ["", self.url]
        return "\n".join(out)

    # ---- LINE Flex ----
    def flex(self) -> dict:
        body: list[dict] = []

        def sep():
            if body:
                body.append({"type": "separator", "margin": "lg", "color": LINE_C})

        for it in self.items:
            k = it[0]
            if k == "section":
                sep()
                head = [{"type": "box", "layout": "vertical", "width": "4px", "height": "14px", "backgroundColor": self.accent, "cornerRadius": "2px", "contents": []},
                        {"type": "text", "text": it[1], "weight": "bold", "size": "md", "color": INK, "flex": 1, "margin": "sm"}]
                if it[2]:
                    head.append({"type": "text", "text": it[2], "size": "xs", "color": MUTED, "align": "end", "flex": 0})
                body.append({"type": "box", "layout": "horizontal", "alignItems": "center", "margin": "lg", "contents": head})
            elif k == "kv" and len(it[2]) > 20:  # 長清單：標題一行、內容一行
                body.append({"type": "box", "layout": "vertical", "margin": "md", "contents": [
                    {"type": "text", "text": it[1], "size": "xs", "color": MUTED},
                    {"type": "text", "text": it[2], "size": "sm", "color": it[3], "wrap": True, "margin": "xs"}]})
            elif k == "kv":
                body.append({"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                    {"type": "text", "text": it[1], "size": "sm", "color": MUTED, "flex": 5, "wrap": True},
                    {"type": "text", "text": it[2], "size": "sm", "color": it[3], "weight": "bold", "align": "end", "flex": 5, "wrap": True}]})
            elif k == "cols":
                body.append({"type": "box", "layout": "horizontal", "margin": "md", "contents": [
                    {"type": "text", "text": " ", "size": "xxs", "flex": 5},
                    {"type": "text", "text": it[1] or " ", "size": "xxs", "color": MUTED, "align": "end", "flex": 3},
                    {"type": "text", "text": it[2] or " ", "size": "xxs", "color": MUTED, "align": "end", "flex": 3}]})
            elif k == "stock":
                _, name, code, mid, right, color, sub, star = it
                left = [{"type": "span", "text": ("★ " if star else "") + name, "weight": "bold", "color": "#F59E0B" if star else INK},
                        {"type": "span", "text": f"  {code}", "size": "xs", "color": MUTED}]
                row = [{"type": "text", "contents": left, "size": "sm", "flex": 5, "wrap": True}]
                if mid:
                    row.append({"type": "text", "text": mid, "size": "xs", "color": MUTED, "align": "end", "flex": 3, "gravity": "center"})
                if right:
                    row.append({"type": "text", "text": right, "size": "sm", "color": color, "weight": "bold", "align": "end", "flex": 3, "gravity": "center"})
                box = {"type": "box", "layout": "vertical", "margin": "md", "contents": [{"type": "box", "layout": "horizontal", "contents": row}]}
                if sub:
                    box["contents"].append({"type": "text", "text": sub, "size": "xs", "color": MUTED, "wrap": True, "margin": "xs"})
                body.append(box)
            elif k == "line":
                body.append({"type": "text", "text": it[1], "size": "sm", "color": it[2], "wrap": True, "margin": "sm", **({"weight": "bold"} if it[3] else {})})
            elif k == "note":
                body.append({"type": "text", "text": it[1], "size": "xxs", "color": MUTED, "wrap": True, "margin": "md"})

        bubble = {
            "type": "bubble", "size": "mega",
            "header": {"type": "box", "layout": "vertical", "backgroundColor": HEAD_BG, "paddingAll": "16px", "contents": [
                {"type": "box", "layout": "vertical", "height": "3px", "width": "36px", "backgroundColor": self.accent, "cornerRadius": "2px", "contents": []},
                {"type": "text", "text": self.title, "color": "#FFFFFF", "weight": "bold", "size": "lg", "wrap": True, "margin": "md"},
                *([{"type": "text", "text": self.subtitle, "color": "#94A3B8", "size": "xs", "wrap": True, "margin": "xs"}] if self.subtitle else []),
            ]},
            "body": {"type": "box", "layout": "vertical", "paddingAll": "16px", "paddingTop": "4px", "contents": body or [{"type": "text", "text": "—", "color": MUTED}]},
        }
        if self.url:
            bubble["footer"] = {"type": "box", "layout": "vertical", "paddingAll": "12px", "contents": [
                {"type": "button", "style": "primary", "height": "sm", "color": self.accent, "action": {"type": "uri", "label": self.button[:20], "uri": self.url}}]}
        alt = (self.title + (f"｜{self.subtitle}" if self.subtitle else ""))[:390]
        return {"type": "flex", "altText": alt, "contents": bubble}
