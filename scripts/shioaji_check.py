#!/usr/bin/env python3
"""
永豐 Shioaji API 開通檢查（一次性，用完會刪掉）
1. 正式環境：用 SHIOAJI_API_KEY 登入（只看行情，不下單），能登入就代表已開通，順便抓一筆台積電快照
2. 模擬環境：有 SHIOAJI_TEST_API_KEY 才做——模擬登入、下一筆模擬股票單（假的單，不會成交、不動到錢），
   這是永豐開通正式環境要求的測試
不會印出任何金鑰內容
"""
import os
import sys
import time

import shioaji as sj


def prod():
    k, s = os.environ.get("SHIOAJI_API_KEY"), os.environ.get("SHIOAJI_SECRET_KEY")
    if not k or not s:
        print("正式：沒有設定 SHIOAJI_API_KEY／SHIOAJI_SECRET_KEY")
        return False
    api = sj.Shioaji()
    try:
        api.login(api_key=k, secret_key=s)
        api.fetch_contracts(contract_download=True)
    except Exception as e:  # noqa: BLE001
        print(f"正式：登入失敗：{e}")
        return False
    try:
        snap = api.snapshots([api.Contracts.Stocks["2330"]])
        print(f"正式：登入成功，台積電快照 {snap[0].close}（{snap[0].change_rate}%）")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"正式：登入成功，但抓行情失敗：{e}")
        return False
    finally:
        api.logout()


def sim():
    k, s = os.environ.get("SHIOAJI_TEST_API_KEY"), os.environ.get("SHIOAJI_TEST_SECRET_KEY")
    if not k or not s:  # 沒有另外放臨時金鑰，就用 SHIOAJI_API_KEY（使用者可直接把它換成有交易權限的金鑰）
        k, s = os.environ.get("SHIOAJI_API_KEY"), os.environ.get("SHIOAJI_SECRET_KEY")
        print("模擬：沒有讀到 SHIOAJI_TEST_*，改用 SHIOAJI_API_KEY 做模擬測試")
    if not k or not s:
        return None
    api = sj.Shioaji(simulation=True)
    try:
        api.login(api_key=k, secret_key=s)
        api.fetch_contracts(contract_download=True)
    except Exception as e:  # noqa: BLE001
        print(f"模擬：登入失敗：{e}")
        return False
    print(f"模擬：登入成功，證券帳戶 {'有' if api.stock_account else '沒有'}")
    c = api.Contracts.Stocks["2890"]
    order = api.Order(price=c.reference, quantity=1, action=sj.Action.Buy, price_type=sj.StockPriceType.LMT,
                      time_in_force=sj.TimeInForce.ROD, order_lot=sj.StockOrderLot.Common, account=api.stock_account)
    try:
        t = api.place_order(c, order)
        print(f"模擬：測試單已送出（永豐金 {c.reference} 買 1 張，模擬單），狀態 {t.status.status}")
        ok = True
    except Exception as e:  # noqa: BLE001
        print(f"模擬：下單失敗：{e}")
        ok = False
    time.sleep(3)
    api.logout()
    return ok


if __name__ == "__main__":
    p = prod()
    s = sim()
    print(f"結果：正式 {'OK' if p else '未開通'}、模擬測試 {'—' if s is None else 'OK' if s else '失敗'}")
    sys.exit(0)
