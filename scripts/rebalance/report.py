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
