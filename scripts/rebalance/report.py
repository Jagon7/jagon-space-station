"""
產出跟原試算表「權重」工作表一樣排版的整理表（值，不是公式）：

  A~D   證券代碼｜收盤價｜原有權重｜預估權重（預估成分股，下面空一列接「剔除」與被剔除的股票，預估權重 0）
  H1    「<ETF>調整_日期」
  H~M   納入｜權重｜金額｜張數｜倍數｜信心
  N~S   剔除｜權重｜金額｜張數｜倍數｜信心
  T~Y   權重調整｜權重｜金額｜張數｜倍數｜信心（續留成分股）
  AE~AK 證券代碼｜權重調整｜預估影響金額｜收盤價｜預估張數｜換手量｜預估影響倍數（AM1 為 AUM）
  AO~AU 同上，依預估影響倍數由大到小排序

「權重」欄是權重調整（新權重 − 原權重）；金額＝權重調整 × ETF 規模（元）；張數＝金額 ÷ (股價 × 1000)；
倍數＝張數 ÷ 換手量（扣除當沖後的成交量，張）。「信心」是原表人工填的，這裡留空。
"""
from __future__ import annotations

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# 跟原試算表相同的格式：權重 0.00%、金額／張數用會計格式、倍數兩位小數、換手量整數
PCT = "0.00%"
PCT3 = "0.00%"
NUM0 = '_-* #,##0_-;\\-* #,##0_-;_-* "-"??_-;_-@_-'
NUM1 = "0"
NUM2 = '_-* #,##0.00_-;\\-* #,##0.00_-;_-* "-"??_-;_-@_-'
PRICE = "General"
YELLOW = PatternFill("solid", fgColor="FFFF00")
HEAD = Font(bold=True)
FILL = {"add": PatternFill("solid", fgColor="FDE2E2"), "del": PatternFill("solid", fgColor="DCF5E3"),
        "adj": PatternFill("solid", fgColor="E3ECFB"), "head": PatternFill("solid", fgColor="EDEDED")}


def _label(code, names):
    n = names.get(code, "")
    return f"{code} {n}".strip()


def _ok(v):
    return v is not None and v == v


def weight_sheet(wb, etf: str, asof: str, final_w: dict, old_w: dict, names: dict, price: dict, turnover: dict,
                 aum_yuan: float, adds: list, dels: list, title: str = "權重"):
    """final_w／old_w：{代號: 權重（小數）}；turnover：{代號: 換手量（千股＝張）}；aum_yuan：ETF 規模（元）。"""
    if title in wb.sheetnames:                     # 明細頁原本也叫「權重」→ 改名，整理表用「權重」
        wb[title].title = f"{title}明細"
    ws = wb.create_sheet(title, 0)
    final = list(final_w)
    keep = [k for k in final if k not in adds]
    rows = {}
    for k in set(final) | set(old_w) | set(dels):
        dw = (final_w.get(k) or 0.0) - (old_w.get(k) or 0.0)
        amt = dw * aum_yuan
        px = price.get(k)
        lots = amt / (px * 1000) if px else None
        tv = turnover.get(k)
        mult = lots / tv if (lots is not None and tv) else None
        rows[k] = (dw, amt, px, lots, tv, mult)

    # A~D 成分股表
    for i, h in enumerate(("證券代碼", "收盤價", "原有權重", "預估權重"), 1):
        c = ws.cell(1, i, h)
        c.font, c.fill = HEAD, FILL["head"]
    r = 2
    for k in final:
        ws.cell(r, 1, _label(k, names))
        ws.cell(r, 2, price.get(k)).number_format = PRICE
        ws.cell(r, 3, old_w.get(k, 0.0)).number_format = PCT
        c = ws.cell(r, 4, final_w[k])
        c.number_format, c.fill = PCT, YELLOW
        r += 1
    ws.cell(r, 3, sum(old_w.get(k, 0.0) for k in final)).number_format = PCT
    ws.cell(r, 4, sum(final_w.values())).number_format = PCT
    r += 1
    ws.cell(r, 1, "剔除").font = HEAD
    r += 1
    for k in dels:
        ws.cell(r, 1, _label(k, names))
        ws.cell(r, 2, price.get(k)).number_format = NUM2
        ws.cell(r, 3, old_w.get(k, 0.0)).number_format = PCT
        ws.cell(r, 4, 0.0).number_format = PCT
        r += 1

    # H1 標題與三個區塊
    t = ws.cell(1, 8, f"{etf}調整_{int(asof[:4])}/{int(asof[5:7])}/{int(asof[8:10])}")
    t.font = Font(bold=True, size=12)

    def block(col, label, codes, kind):
        for i, h in enumerate((label, "權重", "金額", "張數", "倍數", "信心")):
            c = ws.cell(2, col + i, h)
            c.font, c.fill = HEAD, FILL[kind]
        for j, k in enumerate(codes, 3):
            dw, amt, _px, lots, _tv, mult = rows[k]
            ws.cell(j, col, _label(k, names))
            ws.cell(j, col + 1, dw).number_format = PCT3 if kind == "adj" else PCT
            ws.cell(j, col + 2, amt).number_format = NUM0
            ws.cell(j, col + 3, lots).number_format = NUM0
            ws.cell(j, col + 4, mult if _ok(mult) else None).number_format = NUM2
        total = len(codes) + 3
        ws.cell(total, col, "合計").font = HEAD
        ws.cell(total, col + 2, sum(rows[k][1] for k in codes)).number_format = NUM0

    by_mult = lambda ks: sorted(ks, key=lambda k: -(rows[k][5] if _ok(rows[k][5]) else -1e18))  # noqa: E731
    keep = [k for k in keep if old_w.get(k)]
    block(8, "納入", adds, "add")
    block(14, "剔除", dels, "del")
    block(20, "權重調整", keep, "adj")             # 原表：續留成分股（原有、預估權重都不為 0），照成分股表順序

    # AE~AK 影響表、AO~AU 依倍數排序
    heads = ("證券代碼", "權重調整", "預估影響金額", "收盤價", "預估張數", "換手量", "預估影響倍數")
    ws.cell(1, 38, "AUM").font = HEAD
    ws.cell(1, 39, aum_yuan).number_format = NUM0
    order = final + [k for k in dels if k not in final]
    for base, codes in ((31, order), (41, by_mult(order))):
        for i, h in enumerate(heads):
            c = ws.cell(1 if base == 41 else 1, base + i, h)
            c.font, c.fill = HEAD, FILL["head"]
        for j, k in enumerate(codes, 2):
            dw, amt, px, lots, tv, mult = rows[k]
            vals = (_label(k, names), dw, amt, (px or 0) * 1000 if px else None, lots, tv, mult if _ok(mult) else None)
            fmts = (None, PCT3, NUM0, NUM0, NUM0, NUM1, NUM2)
            for i, (v, f) in enumerate(zip(vals, fmts)):
                c = ws.cell(j, base + i, v)
                if f:
                    c.number_format = f

    widths = {1: 16, 2: 9, 3: 9, 4: 9, 8: 16, 14: 16, 20: 16, 31: 16, 41: 16}
    for col in range(1, 48):
        ws.column_dimensions[get_column_letter(col)].width = widths.get(col, 12 if col in (10, 16, 22, 33, 35, 43, 45) else 9)
    ws.freeze_panes = "B2"
    for row in ws.iter_rows(min_row=1, max_row=2):
        for c in row:
            c.alignment = Alignment(vertical="center")
    return ws


# ======================================================================
# ETFRebal_YYMMDD.xlsx：每檔 ETF 一頁的換股整理表（照使用者的 ETFRebal 檔排版）
#   919／56／929：「<簡稱>調整_日期」標題 → 納入／剔除／權重調整三區塊（各依倍數由大到小）
#   50／51：證券代碼｜權重調整｜預估影響金額｜收盤價｜預估張數｜換手量｜預估影養倍數（依倍數排序），下接剔除
# ======================================================================

from openpyxl.formatting.rule import ColorScaleRule  # noqa: E402
from openpyxl.styles import Border, Side  # noqa: E402

FONT = "新細明體"
GREEN, WHITE, RED = "63BE7B", "FCFCFF", "F8696B"
THIN, MED = Side(style="thin"), Side(style="medium")


def _impact(k, final_w, old_w, price, turnover, aum_yuan):
    dw = (final_w.get(k) or 0.0) - (old_w.get(k) or 0.0)
    amt = dw * aum_yuan
    px = price.get(k)
    lots = amt / (px * 1000) if px else None
    tv = turnover.get(k)
    mult = lots / tv if (lots is not None and tv) else None
    return dw, amt, px, lots, tv, mult


def _font_all(ws):
    for row in ws.iter_rows():
        for c in row:
            c.font = Font(name=FONT, size=12, bold=c.font.b)


def rebal_blocks(wb, sheet: str, label: str, asof: str, final_w: dict, old_w: dict, names: dict, price: dict,
                 turnover: dict, aum_yuan: float, adds: list, dels: list, confidence: dict | None = None):
    ws = wb.create_sheet(sheet)
    conf = confidence or {}
    keep = [k for k in final_w if k not in adds and old_w.get(k)]
    data = {k: _impact(k, final_w, old_w, price, turnover, aum_yuan) for k in set(final_w) | set(old_w) | set(dels)}
    key = lambda k: -(data[k][5] if _ok(data[k][5]) else -1e18)  # noqa: E731
    blocks = ((1, "納入", sorted(adds, key=key)), (7, "剔除", sorted(dels, key=key)), (13, "權重調整", sorted(keep, key=key)))
    ws.merge_cells("A1:R1")
    t = ws.cell(1, 1, f"{label}調整_{int(asof[:4])}/{int(asof[5:7])}/{int(asof[8:10])}")
    t.font, t.alignment = Font(name=FONT, size=12, bold=True), Alignment(horizontal="center")
    last = max(len(b[2]) for b in blocks) + 2
    last = max(last, 3)
    for col, head, codes in blocks:
        for i, h in enumerate((head, "權重", "金額", "張數", "倍數", "信心")):
            ws.cell(2, col + i, h)
        for j, k in enumerate(codes, 3):
            dw, amt, _px, lots, _tv, mult = data[k]
            vals = (_label(k, names), dw, amt, lots, mult if _ok(mult) else None, conf.get(k))
            for i, (v, f) in enumerate(zip(vals, (None, PCT, NUM0, NUM0, NUM2, NUM2))):
                c = ws.cell(j, col + i, v)
                if f:
                    c.number_format = f
    # 條件式格式：納入倍數 白→紅、剔除倍數 綠→白、權重調整倍數 綠→白→紅（同使用者檔）
    ws.conditional_formatting.add(f"E3:E{last}", ColorScaleRule(start_type="min", start_color=WHITE,
                                                                end_type="max", end_color=RED))
    ws.conditional_formatting.add(f"K3:K{last}", ColorScaleRule(start_type="min", start_color=GREEN,
                                                                end_type="max", end_color=WHITE))
    ws.conditional_formatting.add(f"Q3:Q{last}", ColorScaleRule(start_type="min", start_color=GREEN,
                                                                mid_type="percentile", mid_value=50, mid_color=WHITE,
                                                                end_type="max", end_color=RED))
    _font_all(ws)
    t.font = Font(name=FONT, size=12, bold=True)
    # 外框粗線、區塊之間細線
    for r in range(1, last + 1):
        for c in range(1, 19):
            cell = ws.cell(r, c)
            left = MED if c == 1 else (THIN if c in (7, 13) else None)
            right = MED if c == 18 else None
            top = MED if r == 1 else (THIN if r == 2 else None)
            bottom = MED if (r == 1 or r == last) else None
            cell.border = Border(left=left or Side(), right=right or Side(), top=top or Side(), bottom=bottom or Side())
    widths = [12.2, 7.2, 15.9, 8.2, 7.2, 6.8] * 3
    widths[0], widths[6], widths[12] = 14.4, 14.4, 16.6
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    return ws


def rebal_table(wb, sheet: str, asof: str, final_w: dict, old_w: dict, names: dict, price: dict, turnover: dict,
                aum_yuan: float, adds: list, dels: list):
    ws = wb.create_sheet(sheet)
    data = {k: _impact(k, final_w, old_w, price, turnover, aum_yuan) for k in set(final_w) | set(old_w) | set(dels)}
    key = lambda k: -(data[k][5] if _ok(data[k][5]) else -1e18)  # noqa: E731
    heads = ("證券代碼", "權重調整", "預估影響金額", "收盤價", "預估張數", "換手量", "預估影養倍數")
    for i, h in enumerate(heads, 1):
        ws.cell(1, i, h)
    fmts = (None, PCT, NUM0, None, NUM0, NUM0, NUM2)

    def put(r, k):
        dw, amt, px, lots, tv, mult = data[k]
        for i, (v, f) in enumerate(zip((_label(k, names), dw, amt, px, lots, tv, mult if _ok(mult) else None), fmts), 1):
            c = ws.cell(r, i, v)
            if f:
                c.number_format = f
    r = 2
    for k in sorted(final_w, key=key):
        put(r, k)
        r += 1
    end = r - 1
    if dels:
        r += 1
        ws.cell(r, 1, "剔除")
        r += 1
        start = r
        for k in sorted(dels, key=key):
            put(r, k)
            r += 1
        for col in ("B", "G"):
            ws.conditional_formatting.add(f"{col}{start}:{col}{r - 1}", ColorScaleRule(
                start_type="min", start_color=GREEN, end_type="max", end_color=WHITE))
    for col in ("B", "G"):
        ws.conditional_formatting.add(f"{col}2:{col}{max(end, 2)}", ColorScaleRule(
            start_type="min", start_color=GREEN, mid_type="percentile", mid_value=50, mid_color=WHITE,
            end_type="max", end_color=RED))
    _font_all(ws)
    for i, w in enumerate((16.6, 9.5, 14.8, 7.5, 9.5, 9.2, 13.9), 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    return ws


def rebal_book(path, asof: str, items: list[dict]):
    """
    items：[{"sheet": "919", "label": "919", "layout": "blocks"|"table", "final_w", "old_w", "names", "price",
             "turnover", "aum_yuan", "adds", "dels", "confidence"}]（照使用者 ETFRebal 檔的頁序）
    """
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for it in items:
        if it.get("missing"):                       # 歷史資料還沒補齊：不給預估，只列缺什麼
            ws = wb.create_sheet(it["sheet"])
            ws.cell(1, 1, f"{it['label']}：資料補齊中，暫不預估").font = Font(name=FONT, size=12, bold=True)
            for i, m in enumerate(it["missing"], 2):
                ws.cell(i, 1, f"缺：{m}").font = Font(name=FONT, size=12)
            ws.column_dimensions["A"].width = 60
            continue
        args = (it["final_w"], it["old_w"], it["names"], it["price"], it["turnover"], it["aum_yuan"], it["adds"], it["dels"])
        if it["layout"] == "blocks":
            rebal_blocks(wb, it["sheet"], it["label"], asof, *args, confidence=it.get("confidence"))
        else:
            rebal_table(wb, it["sheet"], asof, *args)
    wb.save(path)
