#!/usr/bin/env python3
"""
永豐 Shioaji API 開通測試（一次性，用完會刪掉），照官方教學 https://sinotrade.github.io/zh/tutor/prepare/terms/
1. 模擬模式登入、列出帳戶
2. 下一筆模擬證券單：2890 永豐金、限價、ROD、整股、現股、1 張（模擬單不會成交、不動到錢），狀態 Submitted／PendingSubmit 即成功
3. 正式模式登入，看帳戶的 signed 欄位（審核約 5 分鐘，通過後為 True）
金鑰讀 SHIOAJI_TEST_API_KEY，沒有就用 SHIOAJI_API_KEY；不會印出金鑰內容
"""
import faulthandler
import os
import sys
import time

import shioaji as sj

faulthandler.dump_traceback_later(240, exit=True)  # 卡住超過 4 分鐘就印出卡在哪裡並結束


def log(*a):
    print(*a, flush=True)


def keys():
    k, s = os.environ.get("SHIOAJI_TEST_API_KEY"), os.environ.get("SHIOAJI_TEST_SECRET_KEY")
    if not k or not s:
        k, s = os.environ.get("SHIOAJI_API_KEY"), os.environ.get("SHIOAJI_SECRET_KEY")
    return k, s


def accounts(api, tag):
    for a in api.list_accounts():
        log(f"{tag}：帳戶 {type(a).__name__} signed={getattr(a, 'signed', '—')}")


def main():
    k, s = keys()
    if not k or not s:
        log("沒有金鑰")
        return
    log(f"shioaji {sj.__version__}")
    mode = (sys.argv[1] if len(sys.argv) > 1 else "all")
    if mode in ("all", "sim"):
        api = sj.Shioaji(simulation=True)
        log("模擬：登入中…")
        try:
            api.login(api_key=k, secret_key=s)
        except Exception as e:  # noqa: BLE001
            log(f"模擬：登入失敗：{e}")
            return
        log("模擬：登入成功")
        accounts(api, "模擬")
        log("模擬：等商品檔…")  # shioaji 1.7 登入後會自動在背景下載，不能再另外呼叫 fetch_contracts
        c = None
        for _ in range(90):
            try:
                c = api.Contracts.Stocks["2890"]
            except Exception:  # noqa: BLE001
                c = None
            if c is not None:
                break
            time.sleep(1)
        if c is None:
            log("模擬：等不到商品檔，改用手動下載")
            api.fetch_contracts(contract_download=True)
            c = api.Contracts.Stocks["2890"]
        log(f"模擬：2890 參考價 {c.reference}")
        order = api.Order(price=c.reference, quantity=1, action=sj.Action.Buy, price_type=sj.StockPriceType.LMT,
                          time_in_force=sj.TimeInForce.ROD, order_lot=sj.StockOrderLot.Common,
                          order_cond=sj.StockOrderCond.Cash, account=api.stock_account)
        try:
            t = api.place_order(c, order)
            log(f"模擬：測試單已送出，狀態 {t.status.status}（Submitted／PendingSubmit＝成功）")
        except Exception as e:  # noqa: BLE001
            log(f"模擬：下單失敗：{e}")
    if mode in ("all", "prod"):
        if mode == "all":
            time.sleep(2)
        api = sj.Shioaji()
        log("正式：登入中…")
        try:
            api.login(api_key=k, secret_key=s)
            log("正式：登入成功")
            accounts(api, "正式")
        except Exception as e:  # noqa: BLE001
            log(f"正式：登入失敗：{e}")


if __name__ == "__main__":
    main()
    os._exit(0)  # 不等 shioaji 背景連線關閉，避免卡住
