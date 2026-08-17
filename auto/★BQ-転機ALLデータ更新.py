# %%
import socket
socket.setdefaulttimeout(600)
import time
from typing import Optional, Any
import googleapiclient.errors
from googleapiclient.discovery import Resource
import pandas as pd
import datetime
import sqlite3
# import pymysql
import pandas.io.sql as psql
from datetime import datetime as dt
import numpy as np
import pandas.tseries.offsets as offsets
# import sqlalchemy as sqa

# import matplotlib.pyplot as plt
import python_ss.python_ss as ps
import gspread
# from oauth2client.service_account import ServiceAccountCredentials
import json
import gspread

import os
import ast
import db_dtypes
from google.cloud import bigquery
from google.oauth2 import service_account
from google.cloud import secretmanager

# %%
def get_ss(spreadsheet_id: str, range_name: str, service: Resource) -> pd.DataFrame:
    """
    Googleスプレッドシートからデータを取得し、pandas DataFrameとして返します。
    
    特徴:
    - タイムアウト対策済み (socket設定)
    - `fields='values'`による通信量の削減と高速化
    - 1行目をヘッダーとして自動認識（KeyError対策）
    - ネットワークエラー時の自動リトライ機能
    
    Args:
        spreadsheet_id (str): スプレッドシートID
        range_name (str): 範囲指定（例: 'Sheet1!A:M'）
        service (Resource): Google Sheets APIのサービスオブジェクト
        
    Returns:
        pd.DataFrame: 取得したデータ（1行目をカラム名として設定）
    """
    max_retries = 3
    retry_delay = 5  # 初期待機時間（秒）
    
    for attempt in range(max_retries):
        try:
            # スプレッドシートAPIのリクエスト構築
            # 【高速化ポイント】 fields="values" を指定
            # これにより、APIはメタデータを含めず「値のみ」を返すため、
            # レスポンスサイズが小さくなり、通信と解析が高速化します。
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                fields="values"
            ).execute()
            
            values = result.get('values', [])
            
            # データが存在しない場合の処理
            if not values:
                print(f"[{range_name}] データが取得できませんでした（空です）。")
                return pd.DataFrame()

            # 【修正ポイント】1行目をヘッダーとして使用
            # これにより "tenki_id" などのカラム名が正しく認識され、
            # 後の pd.merge 等での KeyError を回避できます。
            header = values[0]
            data = values[1:]
            
            # データ行がある場合のみ作成（ヘッダーのみの場合は空DF）
            if data:
                df = pd.DataFrame(data, columns=header)
            else:
                df = pd.DataFrame(columns=header)
                
            return df

        except (socket.timeout, googleapiclient.errors.HttpError) as e:
            print(f"データ取得中にエラーが発生しました ({attempt + 1}/{max_retries})")
            print(f"エラー詳細: {e}")
            
            # 最大回数失敗したらエラーを発生させる
            if attempt == max_retries - 1:
                print("最大リトライ回数に達しました。処理を中断します。")
                raise e
            
            # エクスポネンシャルバックオフ（待機時間を徐々に延ばす）
            wait_time = retry_delay * (2 ** attempt)
            print(f"{wait_time}秒待機して再試行します...")
            time.sleep(wait_time)

    return pd.DataFrame()

# %%
def access_secret_version(project_id, secret_id, version_id='latest'):
    client = secretmanager.SecretManagerServiceClient()

    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    payload = response.payload.data.decode("UTF-8")
    return ast.literal_eval(payload)

# %%
# 上記関数を実行するコードが記載されています。こちらもそのままお使いください。
credentials = service_account.Credentials.from_service_account_info(
access_secret_version('r-group-bigdata', 'CREDENTIALS_SECRET_KEY_WORKER'),
scopes=["https://www.googleapis.com/auth/cloud-platform"],)


# %%
pd.set_option('display.max_rows', 50)
pd.set_option('display.max_columns', None)

# %% [markdown]
# ## 重複管理シート_マスタ_更新

# %%
#登録重複シート更新用の認証・シート設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
          'https://www.googleapis.com/auth/spreadsheets']
json_path = r"Z:\Users\suehara\Documents\python\analysis\python_ss\credentials.json"
service = ps.get_auth(SCOPES,json_path)
SPREADSHEET_ID = '15qRR-yfJxgCh_TpXwBjBHNAnc8yAeTUCF0-Y_N6GoIo'


# %% [markdown]
# ## 転機内重複確認

# %%
qry = """
SELECT 
  id,
	simei_tyofuku,
	tel_tyofuku
FROM `r-group-bigdata.live_tenki.user_tyofuku`
order by id
"""

client = bigquery.Client(credentials=credentials, project=credentials.project_id)
tktyofuku = client.query(qry).result().to_dataframe()

# %%
tyofuku = tktyofuku

# %%
tyofuku

# %%
tyofuku["id"] = tyofuku["id"].astype(str) 

tyofuku.replace([np.inf, -np.inf], np.nan, inplace=True)
tyofuku.fillna('', inplace=True)
tyofuku = tyofuku.values.tolist()

# %%
service = ps.get_auth(SCOPES, json_path)
Sheet_NAME_jokyo = '登録重複シート!A'
Sheet_row_jokyo = '2'
RANGE_NAME_jokyo = Sheet_NAME_jokyo+Sheet_row_jokyo
ps.update_ss(SPREADSHEET_ID,RANGE_NAME_jokyo,tyofuku,service)

# %% [markdown]
# ## 手上げ単価計測の候補者マスタ更新

# %%
#2020年1月以降の手上げ情報取得
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
          'https://www.googleapis.com/auth/spreadsheets']
json_path = r"C:\Users\suehara\Desktop\お転機BOX\ぱいそん練習\python_ss\credentials.json"
service = ps.get_auth(SCOPES,json_path)
SPREADSHEET_ID = '15qRR-yfJxgCh_TpXwBjBHNAnc8yAeTUCF0-Y_N6GoIo'
Sheet_NAME = 'マスタ!A'
Sheet_row = ":B"
RANGE_NAME = Sheet_NAME+Sheet_row
tkinfo = get_ss(SPREADSHEET_ID,RANGE_NAME,service)

# %%
data = tkinfo.copy()
data["ID"] = data["ID"].astype(int)
data = data.query('ID >= 46273') #28953

# %%
#2019年9月以降の手上げ情報取得
SPREADSHEET_ID = '1fOGhqvCoER3YYv2npDUT1KAB6Fw9fYfQ29Vf52p5Nts'
Sheet_NAME = '候補者状況!A'
Sheet_row = ":S"
RANGE_NAME = Sheet_NAME+Sheet_row
pastteageinfo = get_ss(SPREADSHEET_ID,RANGE_NAME,service)
pastteageinfo["ID"] = pastteageinfo["ID"].astype(int)
pastteageinfo = pastteageinfo.query('ID >= 46273') #28953
pastteageinfo["ID"] = pastteageinfo["ID"].astype(str)
pastteageinfo = pastteageinfo[["ID","登録日時","フリ先","手あげ日付","本手上げ","KN共有日"]]
pastteageinfo

# %%
#2020年1月以降の手上げ情報取得
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
          'https://www.googleapis.com/auth/spreadsheets']
json_path = r"C:\Users\suehara\Desktop\お転機BOX\ぱいそん練習\python_ss\credentials.json"
service = ps.get_auth(SCOPES,json_path)
SPREADSHEET_ID = '15qRR-yfJxgCh_TpXwBjBHNAnc8yAeTUCF0-Y_N6GoIo'
Sheet_NAME = '候補者状況!A'
Sheet_row = ":Y"
RANGE_NAME = Sheet_NAME+Sheet_row
teageinfo = get_ss(SPREADSHEET_ID,RANGE_NAME,service)
teageinfo["ID"] = teageinfo["ID"].astype(int)
teageinfo = teageinfo.query('ID > 74999') #28953
teageinfo["ID"] = teageinfo["ID"].astype(str)
teageinfo = teageinfo[["ID","登録日時","フリ先","手あげ日付","本手上げ","KN共有日"]]
teageinfo

# %%
teageinfo = pd.concat([pastteageinfo,teageinfo],axis=0,ignore_index=True)
koshinLIST = teageinfo.copy()
data["ID"] = data["ID"].astype(str)
koshinLIST = pd.merge(data,koshinLIST,how="left",on="ID")
koshinLIST = koshinLIST.drop(columns=["登録日時"])
koshinLIST.replace([np.inf, -np.inf], np.nan, inplace=True)
koshinLIST.fillna('', inplace=True)
koshinLIST = koshinLIST.values.tolist()

# %%
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
          'https://www.googleapis.com/auth/spreadsheets']
json_path = r"C:\Users\suehara\Desktop\お転機BOX\ぱいそん練習\python_ss\credentials.json"
service = ps.get_auth(SCOPES,json_path)
SPREADSHEET_ID = '14vXxjcdlyY463QjrtEnCw7pJ0oLStXZD8Q42IdW2Zd4'
service = ps.get_auth(SCOPES, json_path)
Sheet_NAME = '候補者マスタ!A'
Sheet_row = "184"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,koshinLIST,service)

#1r_ceqW-WvUNSCJs7DvJvme7D0q6H4nx-pVeojpQMCfU

# %% [markdown]
# ## 未手上げファイル更新

# %%
miteage_qry = """
select
	inf.id as tenki_id,
  format_date('%Y/%m/%d',inf.created_at) as torokubi,
	inf.shi as sei,
	inf.mei as mei,
	inf.shi_kana as sei_kana,
	inf.mei_kana as mei_kana,
	"11" as ap_source,
	inf.comp_name as company,
	inf.gyousyu1 as gyoshu,
	inf.syokusyu1 as shokushu,
	inf.layer,
	inf.pref,
	inf.work_pref,
	inf.income,
  EXTRACT(YEAR FROM inf.created_at) - birth_year as nenrei,
	inf.seibetu,
	inf.wish_pref,
	inf.moving,
	concat(inf.birth_year,"/",inf.birth_month,"/",inf.birth_day) as birth_day,
	inf.mob_tel as phon_number,
	inf.email,
    dtl.youyaku
from `r-group-bigdata.live_tenki.user_info` inf
left join `r-group-bigdata.live_tenki.user_detail` dtl on inf.id = dtl.id  
where	replace(inf.shi," ","") != ""
AND	replace(inf.mei," ","") != ""
AND	inf.created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH)
order by inf.id
"""

client = bigquery.Client(credentials=credentials, project=credentials.project_id)
miteage = client.query(miteage_qry).result().to_dataframe()


# %%
miteageA = miteage

# %%
path1 = "//172.16.0.232/CoffeeCrazy3/新規事業室（藤社長）/転機_候補者対応関連/ユーザー情報/未手あげデータ/未手あげ候補者インポート_1.2.xlsx"
path1

# %%
# miteageA = miteageA.applymap(remove_control_characters)

# %%
# 制御文字(0x00-0x1f)を除去してExcelに書き込む
# applymapでPython関数を1セルずつ適用するより、正規表現replaceでベクトル化した方が高速
miteageA = miteageA.replace(to_replace=r'[\x00-\x1f]', value='', regex=True)

with pd.ExcelWriter(path1, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
    miteageA.to_excel(writer, sheet_name='userinfo', startrow=0, startcol=0, index=False)


# %%


# %% [markdown]
# ## 候補者マスタ情報更新

# %%

SPREADSHEET_ID = '14vXxjcdlyY463QjrtEnCw7pJ0oLStXZD8Q42IdW2Zd4'
Sheet_NAME = '候補者マスタ!'
Sheet_RANGE = "A:B"
RANGE_NAME = Sheet_NAME+Sheet_RANGE
tkinfo = get_ss(SPREADSHEET_ID,RANGE_NAME,service)

# %%
SPREADSHEET_ID = '15qRR-yfJxgCh_TpXwBjBHNAnc8yAeTUCF0-Y_N6GoIo'
Sheet_NAME = 'マスタ!'
Sheet_RANGE = "A:Y"
RANGE_NAME = f"{Sheet_NAME}{Sheet_RANGE}"

# スプレッドシートからデータ取得
tkmasta = get_ss(SPREADSHEET_ID, RANGE_NAME, service)

# 3. 必要なカラムのみ抽出（メモリ使用量の最小化）
tkmasta = tkmasta[["ID", "age", "layer", "income", "change_job", "comp_name", "syokusyu1", "jokin"]]

# %%
tkinfo

# %%
tkinfo = tkinfo.rename(columns={"tenki_id":"ID"})
tkinfo = pd.merge(tkinfo,tkmasta,how="left",on="ID")

# %%
import pandas as pd
import numpy as np # pd.isna を使う場合や NaN 処理で必要になる可能性

# --- 1. tkinfo["income"] の変換 ---
print("income カラムの変換を開始...")

# 変換ルールを辞書で定義
income_map = {
    "300万円未満": 200,
    "300～399万円": 300,
    "400～499万円": 400,
    "500～599万円": 500,
    "600～699万円": 600,
    "700～799万円": 700,
    # "800～999万円": 800, # 注意: 下の 800-899, 900-999 と重複。どちらが正しいかご確認ください。リスト通りに含めています。
    "800～899万円": 800,
    "900～999万円": 900,
    "1000～1099万円": 1000,
    "1100～1199万円": 1100,
    "1200～1299万円": 1200,
    "1300～1399万円": 1300,
    "1400～1499万円": 1400,
    "1500～1599万円": 1500,
    "1600～1699万円": 1600,
    "1700～1799万円": 1700,
    "1800～1899万円": 1800,
    "1900～1999万円": 1900,
    "2000万円以上": 2000,
    "2000～2999万円": 2000,
    "3000～3999万円": 3000,
    "4000～4999万円": 4000,
    "5000万円以上": 5000,
}

# .map() を使って値を変換し、元のカラムを上書き
tkinfo["income"] = tkinfo["income"].map(income_map)

# 注意: マッピング辞書にない元の値は NaN になります。
# 必要であれば、NaN を特定の値 (例: 0 や -1) で埋める処理を追加してください。
# 例: tkinfo["income"] = tkinfo["income"].fillna(0)

print("income カラムの変換完了。")


# --- 2. tkinfo["change_job"] の変換 ---
print("change_job カラムの変換を開始...")

# 変換ルールを辞書で定義
change_job_map = {
    "転職経験なし": 0,
    "1回（2社経験）": 1,
    "2回（3社経験）": 2,
    "3回（4社経験）": 3,
    "4回（5社経験）": 4,
    "5回（6社経験）": 5,
    "6回（7社経験）": 6,
    "7回（8社経験）": 7,
    "8回（9社経験）": 8,
    "9回（10社経験）": 9,
    "10回以上（11社以上経験）": 10
}

# .map() を使って値を変換し、元のカラムを上書き
tkinfo["change_job"] = tkinfo["change_job"].map(change_job_map)

# 注意: マッピング辞書にない元の値は NaN になります。
# 必要であれば、NaN を特定の値 (例: -1 など) で埋める処理を追加してください。
# 例: tkinfo["change_job"] = tkinfo["change_job"].fillna(-1)

print("change_job カラムの変換完了。")

# --- 3. tkinfo["jokin"] の変換 ---
print("jokin カラムの変換を開始...")

# 変換ルールを適用する関数を定義 (None, NaN, 数値を安全に処理)
def convert_jokin_status(jokin_value):
    """jokinカラムの値を指定された文字列に変換する"""
    if pd.isna(jokin_value): # None または NaN の場合
        return '特に問わない'
    try:
        jokin_int = int(jokin_value) # 比較のために整数に変換試行
        if jokin_int == 3:
            return '特に問わない'
        elif jokin_int == 0:
            return '常勤'
        elif jokin_int == 1:
            return '非常勤（週2-3日）'
        elif jokin_int == 2:
            return '非常勤（月2-3日' # 指示通りの文字列
        else:
            # 0, 1, 2, 3 以外の数値の場合 (そのまま返すか、エラーとするかなど)
            return jokin_value # ここでは元の値を返す
    except (ValueError, TypeError):
        # 文字列など、整数に変換できない場合 (そのまま返すか、エラーとするかなど)
        return jokin_value # ここでは元の値を返す

# .apply() を使って関数を適用し、元のカラムを上書き
tkinfo['jokin'] = tkinfo['jokin'].apply(convert_jokin_status)

print("jokin カラムの変換完了。")

# %%
tkinfo = tkinfo[['age', 'layer', 'income', 'change_job', 'comp_name','syokusyu1', 'jokin']]

# %%
display(tkinfo.tail(10))

# %%
tkinfo.replace([np.inf, -np.inf], np.nan, inplace=True)
tkinfo.fillna('', inplace=True)
tkinfo = tkinfo.values.tolist()

# %%
SPREADSHEET_ID = '14vXxjcdlyY463QjrtEnCw7pJ0oLStXZD8Q42IdW2Zd4'
service = ps.get_auth(SCOPES, json_path)
Sheet_NAME = '候補者マスタ!L'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,tkinfo,service)

