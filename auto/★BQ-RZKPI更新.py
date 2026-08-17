# %%
import socket
import time
import googleapiclient.errors
import pandas as pd
import datetime
import sqlite3
import pymysql
import pandas.io.sql as psql
from datetime import datetime as dt
import numpy as np
import pandas.tseries.offsets as offsets
# import sqlalchemy as sqa
# import matplotlib.pyplot as plt
import python_ss.python_ss as ps
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

import os
import ast
import db_dtypes
from google.cloud import bigquery
from google.oauth2 import service_account
from google.cloud import secretmanager
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# %%
# 【重要】タイムアウト設定
# デフォルトのタイムアウト時間を10分（600秒）に設定します。
# データ量が多い場合、ここを延ばすことでTimeoutErrorを防ぎます。
socket.setdefaulttimeout(600)

# %%
def access_secret_version(project_id, secret_id, version_id='latest'):
    client = secretmanager.SecretManagerServiceClient()

    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    payload = response.payload.data.decode("UTF-8")
    return ast.literal_eval(payload)

# %%
def get_ss_optimized(spreadsheet_id, range_name, service):
    """
    スプレッドシートのデータを取得する関数（高速化・安定化・ヘッダー対応版）
    
    Args:
        spreadsheet_id (str): スプレッドシートID
        range_name (str): 範囲指定（例: 'Sheet1!A:M'）
        service (obj): Google Sheets APIのサービスオブジェクト
        
    Returns:
        pd.DataFrame: 取得したデータのDataFrame（1行目をヘッダーとして処理）
    """
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            sheet = service.spreadsheets()
            
            # 【高速化ポイント】 fields='values' を指定
            # これにより、APIはメタデータを含めず「値のみ」を返すため、
            # レスポンスサイズが小さくなり、通信と解析が高速化します。
            result = sheet.values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                fields="values" 
            ).execute()
            
            values = result.get('values', [])
            
            # データが存在しない場合の処理
            if not values:
                print("データが取得できませんでした（空です）。")
                return pd.DataFrame()

            # 【修正ポイント】1行目をヘッダーとして使用する処理を追加
            # values[0]をカラム名、values[1:]をデータ本体としてDataFrameを作成
            header = values[0]
            data = values[1:]
            
            # データ行がある場合のみ作成（ヘッダーのみの場合は空DF）
            if data:
                df = pd.DataFrame(data, columns=header)
            else:
                df = pd.DataFrame(columns=header)
                
            return df

        except (socket.timeout, googleapiclient.errors.HttpError) as e:
            # タイムアウトや一時的なエラーが発生した場合、少し待ってから再試行する
            print(f"データ取得中にエラーが発生しました。再試行します ({attempt + 1}/{max_retries})...")
            print(f"エラー詳細: {e}")
            if attempt == max_retries - 1:
                # 最大回数失敗したらエラーを発生させる
                raise e
            time.sleep(5 * (attempt + 1)) # 待機時間を徐々に延ばす

# %%
# ※ ps.get_auth は既存のモジュールを使用されている前提です
# service = ps.get_auth(SCOPES, json_path) 
# ↓ 動作確認用ダミー変数（実際は上の行のコメントアウトを外してserviceを作成してください）
service = None 

# %%


# %%
# 上記関数を実行するコードが記載されています。こちらもそのままお使いください。
credentials = service_account.Credentials.from_service_account_info(
  access_secret_version('temp-for-sandbox', 'TEMP_CREDENTIAL_KEY'),
  scopes=["https://www.googleapis.com/auth/cloud-platform"],)

# %%
# 上記関数を実行するコードが記載されています。こちらもそのままお使いください。
credentials = service_account.Credentials.from_service_account_info(
access_secret_version('r-group-bigdata', 'CREDENTIALS_SECRET_KEY_WORKER'),
scopes=["https://www.googleapis.com/auth/cloud-platform"],)


# %%
pd.set_option('display.max_rows', 100)
pd.set_option('display.max_columns', None)

# %%
# BigQueryクライアントは1度だけ生成し、以降のクエリで再利用する（高速化）
client = bigquery.Client(credentials=credentials, project=credentials.project_id)

# %% [markdown]
# ## 登録情報更新

# %%
#転機IDの10000以降の手上げ情報取得
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
          'https://www.googleapis.com/auth/spreadsheets']
json_path = r"Z:\Users\suehara\Documents\python\analysis\python_ss\credentials.json"
service = ps.get_auth(SCOPES,json_path)
SPREADSHEET_ID = '15qRR-yfJxgCh_TpXwBjBHNAnc8yAeTUCF0-Y_N6GoIo'
Sheet_NAME = '候補者状況!A'
Sheet_row = ":S"
RANGE_NAME = Sheet_NAME+Sheet_row
teageinfo = get_ss_optimized(SPREADSHEET_ID,RANGE_NAME,service)
teageinfo = teageinfo[["ID","登録日時","処理フラグ","フリ先","手あげ日付","担当","手あげ","KN共有日"]]
teageinfo["ID"] = teageinfo["ID"].fillna(0)
teageinfo["ID"] = teageinfo["ID"].astype(int)
teageinfo = teageinfo[teageinfo["ID"] >= 75000]


# %%
teageinfo

# %%
#転機IDの46273~74999の手上げ情報取得
SPREADSHEET_ID = '1fOGhqvCoER3YYv2npDUT1KAB6Fw9fYfQ29Vf52p5Nts'
Sheet_NAME = '候補者状況!A'
Sheet_row = ":S"
RANGE_NAME = Sheet_NAME+Sheet_row
pastteageinfo = get_ss_optimized(SPREADSHEET_ID,RANGE_NAME,service)
pastteageinfo = pastteageinfo[["ID","登録日時","処理フラグ","フリ先","手あげ日付","担当","手あげ","KN共有日"]]
pastteageinfo["ID"] = pastteageinfo["ID"].fillna(0)
pastteageinfo["ID"] = pastteageinfo["ID"].astype(int)
# pastteageinfo = pastteageinfo[pastteageinfo["ID"] >= 46273]


# %%
pastteageinfo["ID"] = pastteageinfo["ID"].fillna(0)
teageinfo = pd.concat([pastteageinfo,teageinfo],axis=0,ignore_index=True)
teageinfo["ID"] = teageinfo["ID"].fillna(0)
teageinfo["ID"] = teageinfo["ID"].astype(str)
teageinfoA = teageinfo.copy()

# %%
teageinfo

# %%
#重複管理シートのマスタから全転機IDを取得
SPREADSHEET_ID = '15qRR-yfJxgCh_TpXwBjBHNAnc8yAeTUCF0-Y_N6GoIo'
Sheet_NAME = 'マスタ!A'
Sheet_row = ":Y"
RANGE_NAME = Sheet_NAME+Sheet_row
tktoroku = get_ss_optimized(SPREADSHEET_ID,RANGE_NAME,service)


# %%
tktoroku.columns

# %%
tktoroku["ID"] = tktoroku["ID"].astype(int)
tktoroku = tktoroku.rename(columns={"ID":"tenki_id"})
tktoroku = tktoroku.query('tenki_id >= 46273')

teageinfoA = teageinfoA.rename(columns={"ID":"tenki_id"})

tktoroku["tenki_id"] = tktoroku["tenki_id"].astype(str)
tktoroku = pd.merge(tktoroku,teageinfoA,how="left",on=("tenki_id"))
tktoroku = tktoroku.rename(columns={"tenki_id":"転機ID","フリ先":"事業部","処理フラグ":"結果"})
tktoroku = tktoroku[["転機ID","created_at","結果","事業部","手あげ日付","担当","手あげ","KN共有日","age", 'jokin']]


# %%
# 変換ルールを適用する関数を定義
def convert_jokin_status(jokin_value):
    """jokinカラムの値を指定された文字列に変換する"""
    if pd.isna(jokin_value): # None または NaN の場合
        return '特に問わない'
    try:
        # 比較のために整数に変換しようと試みる (元の型がfloatの可能性があるため)
        # 文字列などが混入している場合は except に飛ぶ
        jokin_int = int(jokin_value)

        if jokin_int == 3:
            return '特に問わない'
        elif jokin_int == 0:
            return '常勤'
        elif jokin_int == 1:
            return '非常勤（週2-3日）'
        elif jokin_int == 2:
            return '非常勤（月2-3日' # 指示通りの文字列
        else:
            # 0, 1, 2, 3 以外の場合は元の値をそのまま返す (必要に応じて変更)
            return jokin_value
    except (ValueError, TypeError):
        # 整数に変換できない場合 (例: 文字列など) は元の値を返す (必要に応じて変更)
        return jokin_value

# .apply() を使って関数を 'jokin' カラムに適用し、新しいカラム 'jokin_text' を作成
tktoroku['jokin'] = tktoroku['jokin'].apply(convert_jokin_status)

# %%
tktoroku

# %%
tktoroku_work = tktoroku.copy()

# %%
tktoroku_work.replace([np.inf, -np.inf], np.nan, inplace=True)
tktoroku_work.fillna('', inplace=True)

tktoroku_work = tktoroku_work.values.tolist()

# %%
#スプレッドシートに記載する
SPREADSHEET_ID = '1ofer5LQADQ9ppKrtQWWbOyhyEmcrBx_c_O4UmVFe3wU'
Sheet_NAME = '登録!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,tktoroku_work,service)

# %% [markdown]
# ## 広告情報取得

# %%
#最後のIDを取得する
SPREADSHEET_ID = '14vXxjcdlyY463QjrtEnCw7pJ0oLStXZD8Q42IdW2Zd4'
Sheet_NAME = '候補者マスタ!A'
Sheet_row = ":M"
RANGE_NAME = Sheet_NAME+Sheet_row
adinfo = get_ss_optimized(SPREADSHEET_ID, RANGE_NAME, service)


# %%
adinfoA = adinfo.copy()

# %%
adinfoA.replace([np.inf, -np.inf], np.nan, inplace=True)
adinfoA.fillna('', inplace=True)
adinfoA = adinfoA.values.tolist()

# %%
adinfo

# %% [markdown]
# ## 初期交渉

# %%
rzshokikosho_query = """
WITH
-- =================================================================
-- マスタデータ準備セクション
-- 必要なマスタデータを事前にCTEとして定義し、再利用しやすくする
-- =================================================================

-- CTE 1: APソースのマスタデータ (group_code = 19)
ap_source_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 19
),

-- CTE 2: 移籍意欲のマスタデータ (group_code = 5100)
iseki_iyoku_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 5100
),

-- =================================================================
-- 基本データ作成セクション
-- 必要なテーブルを結合し、基本的なカラムを計算する
-- =================================================================
base_data AS (
  SELECT
    shoki.kohosha_id,
    shoki.tenki_id,
    shoki.kosho_setteibi,
    shoki.kosho_yoteibi,
    shoki.kosho_jisshibi,
    shoki.kosho_seq,
    shoki.cxl_riyu,
    shoki.valid_flag,
    -- APsourceを分かりやすいカテゴリに分類
    CASE
      WHEN consts.name IN ('HP反響', '上場企業役員DM', 'Gアポ') THEN 'その他'
      WHEN consts.name = '社外取締役名鑑　候補者' THEN '顧問名鑑登録　解放者'
      ELSE consts.name
    END AS APsource,
    syi2.sei_plus AS ap_kakutokusha,
    COALESCE(syi1.sei_plus, shoki.mendan_tanto) AS mendan_tanto,
    -- 交渉のステータスを判定
    CASE
      WHEN shoki.kosho_yoteibi >= CURRENT_DATE("Asia/Tokyo") THEN '実施前'
      WHEN shoki.jisshi_flag = 2 AND shoki.deleted = 2 THEN "CXL"
      WHEN shoki.jisshi_flag = 0 AND shoki.deleted = 0 AND shoki.nittei_chosei = 1 THEN "日程調整中"
      WHEN shoki.jisshi_flag = 1 THEN '実施'
      WHEN shoki.jisshi_flag = 0 THEN '未報告'
      ELSE CAST(shoki.jisshi_flag AS STRING)
    END AS jisshi_status,
    -- 移籍意欲を候補者マスタと初期交渉テーブルから取得し、優先度付け
    COALESCE(consts2.name, consts3.name) AS iseki_iyoku
  FROM
    -- `r-group-bigdata..live_rhs.shokikoshos` の typo `..` を修正
    `r-group-bigdata.live_rhs.shokikoshos` AS shoki
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` AS khs ON shoki.kohosha_id = khs.id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON shoki.mendan_tanto = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON shoki.ap_kakutoku = syi2.user_id
    LEFT JOIN ap_source_master AS consts ON shoki.ap_source = consts.code
    LEFT JOIN iseki_iyoku_master AS consts2 ON khs.iseki_iyoku_new = consts2.code
    LEFT JOIN iseki_iyoku_master AS consts3 ON shoki.iseki_iyoku = consts3.code
),

-- =================================================================
-- ウィンドウ関数を用いた特徴量計算セクション
-- =================================================================
feature_calculation AS (
  SELECT
    *,
    -- 前回交渉実施日からの経過日数を計算
    DATE_DIFF(kosho_setteibi, LAG(kosho_jisshibi) OVER (PARTITION BY kohosha_id ORDER BY kosho_setteibi), DAY) AS keikabi,
    -- 前回のAPsourceを取得
    LAG(APsource) OVER (PARTITION BY kohosha_id ORDER BY kosho_setteibi) AS prev_APsource
  FROM
    base_data
)

-- =================================================================
-- 最終的なフラグ計算とデータ絞り込み
-- =================================================================
SELECT
  kohosha_id,
  tenki_id,
  APsource,
  ap_kakutokusha,
  mendan_tanto,
  kosho_setteibi,
  kosho_yoteibi,
  kosho_jisshibi,
  jisshi_status,
  kosho_seq,
  cxl_riyu,
  iseki_iyoku,
  -- APsourceが前回から変更されたかを判定
  CASE
    WHEN APsource != prev_APsource THEN 1
    ELSE 0
  END AS APS_change,
  -- sai_flgを計算
  CASE
    WHEN kosho_seq = 1 THEN 1 -- 初回交渉
    WHEN APsource != prev_APsource THEN 1 -- APソースが変更
    WHEN keikabi > 90 THEN 2 -- 前回実施から90日以上経過
    ELSE 0
  END AS sai_flg
FROM
  feature_calculation
WHERE
  APsource = '転機社長名鑑'
  AND kosho_setteibi >= DATE '2019-10-01'
ORDER BY
  kosho_setteibi DESC;


"""

rzshokikosho = client.query(rzshokikosho_query).result().to_dataframe()


# %%
rzshokikosho1 = rzshokikosho.copy()

# %%
adinfo = adinfo.rename(columns={"ID":"tenki_id"})

# %%
rzshokikosho["tenki_id"] = rzshokikosho["tenki_id"].astype(str)
rzshokikosho = pd.merge(rzshokikosho,adinfo,on=("tenki_id"),how=("left"))

# %%
adinfo

# %%
rzshokikosho = rzshokikosho[["kohosha_id","tenki_id","APsource",
                             "ap_kakutokusha","mendan_tanto","登録日時","kosho_setteibi","kosho_yoteibi",
                             "kosho_jisshibi","jisshi_status","sai_flg","APS_change","kosho_seq","手上げ日付","フリ先","KN共有日","iseki_iyoku",
                             "参照元/メディア","キャンペーン","広告ID"]]

# %%
rzshokikosho["tenki_id"] = rzshokikosho["tenki_id"].astype(str).str.replace('<NA>', '')
rzshokikosho["kohosha_id"] = rzshokikosho["kohosha_id"].astype(str)

rzshokikosho["登録日時"] = rzshokikosho["登録日時"].astype(str).str.replace('nan', '')
rzshokikosho["kosho_setteibi"] = rzshokikosho["kosho_setteibi"].astype(str) 
rzshokikosho["kosho_yoteibi"] = rzshokikosho["kosho_yoteibi"].astype(str)
rzshokikosho["kosho_jisshibi"] = rzshokikosho["kosho_jisshibi"].astype(str).str.replace('None', '')
rzshokikosho["KN共有日"] = rzshokikosho["KN共有日"].astype(str).str.replace('nan', '')

# %%
rzshokikosho

# %%
rzshokikosho.replace([np.inf, -np.inf], np.nan, inplace=True)
rzshokikosho.fillna('', inplace=True)

rzshokikosho = rzshokikosho.values.tolist()

# %%
#転機KPIシートに記載する
SPREADSHEET_ID = '1ofer5LQADQ9ppKrtQWWbOyhyEmcrBx_c_O4UmVFe3wU'
Sheet_NAME = '初期交渉!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,rzshokikosho,service)


# %%
tktoroku = tktoroku.rename(columns={"転機ID":"tenki_id"})
rzshokikosho1["tenki_id"] = rzshokikosho1["tenki_id"].astype(str)
rzshokikosho1 = pd.merge(rzshokikosho1,tktoroku,on=("tenki_id"),how=("left"))
rzshokikosho1 = rzshokikosho1[["kohosha_id","tenki_id","APsource",
                             "ap_kakutokusha","mendan_tanto","created_at","kosho_setteibi","kosho_yoteibi",
                             "kosho_jisshibi","jisshi_status","sai_flg","APS_change","kosho_seq","手あげ日付","手あげ","KN共有日"]]

rzshokikosho1["tenki_id"] = rzshokikosho1["tenki_id"].astype(str).str.replace('<NA>', '')
rzshokikosho1["kohosha_id"] = rzshokikosho1["kohosha_id"].astype(str)

rzshokikosho1["created_at"] = rzshokikosho1["created_at"].astype(str).str.replace('nan', '')
rzshokikosho1["kosho_setteibi"] = rzshokikosho1["kosho_setteibi"].astype(str) 
rzshokikosho1["kosho_yoteibi"] = rzshokikosho1["kosho_yoteibi"].astype(str)
rzshokikosho1["kosho_jisshibi"] = rzshokikosho1["kosho_jisshibi"].astype(str).str.replace('None', '')
rzshokikosho1["KN共有日"] = rzshokikosho1["KN共有日"].astype(str).str.replace('nan', '')

rzshokikosho1.replace([np.inf, -np.inf], np.nan, inplace=True)
rzshokikosho1.fillna('', inplace=True)

rzshokikosho1 = rzshokikosho1.values.tolist()

# %%
#メンバー別未来AP数シートに記載する
SPREADSHEET_ID = '1EFxWeFN9b2kWU1qAy98KmjEm9n63-p61HiurqZkEWlQ'
Sheet_NAME = '初期交渉!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,rzshokikosho1,service)


# %%
#KN×転機シートに記載する
SPREADSHEET_ID = '1rWQ_WfeSsublthKuDmRXf_fNcPwdjvx6chZGK1xxUBM'
Sheet_NAME = '初期交渉!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,rzshokikosho,service)


# %%
#KN×転機シートに記載する
SPREADSHEET_ID = '1qtTngN03WSZ_JjZovhNVh6bd1uc_Eh8tRP5Hp9yWSNc'
Sheet_NAME = 'shoki!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,rzshokikosho,service)

# %% [markdown]
# ## 本交渉データ

# %%
rzhonkosho_query = """
with HONS as (
with SHOKIS as (
with shoki_base3 as (
with shoki_base2 as (
with shoki_base as (
SELECT
  shk.id,
  shk.tenki_id,
  shk.kohosha_id,
  shk.ap_source,
  case when syi1.sei_plus is null then shk.mendan_tanto
       else syi1.sei_plus end as mendan_tanto,
  syi2.sei_plus as ap_kakutokusha,
  shk.kosho_setteibi,
  shk.kosho_yoteibi,
  shk.kosho_jisshibi,
  consts2.name as iseki_iyoku,
  shk.kosho_seq,
  shk.saikosho_kaisu,
  saikosho_seq,
  valid_flag,
  DATE_DIFF(kosho_jisshibi, LAG(kosho_jisshibi) OVER (PARTITION BY kohosha_id ORDER BY kosho_jisshibi), DAY) AS keikabi
  FROM `r-group-bigdata.live_rhs.shokikoshos` shk
  left join `r-group-bigdata.live_rhs.kohoshas` khs on shk.kohosha_id = khs.id
  left join `r-group-bigdata.live_company.syain` syi1 on shk.mendan_tanto = syi1.user_id
  left join `r-group-bigdata.live_company.syain` syi2 on shk.ap_kakutoku = syi2.user_id
  left join (SELECT code,name
             FROM `r-group-bigdata.live_rhs.sys_consts` where group_code = 19) consts on shk.ap_source = consts.code
  left join (SELECT code,name
             FROM `r-group-bigdata.live_rhs.sys_consts` where group_code = 5100) consts2 ON shk.iseki_iyoku = consts2.code
  order by shk.kosho_setteibi)

  select *,
    LAG(ap_source) OVER (PARTITION BY kohosha_id ORDER BY kosho_setteibi) AS prev_APsource,
  from shoki_base)

  select *,
   CASE WHEN ap_source != prev_APsource THEN 1 ELSE 0
        END AS APS_change
  from shoki_base2)

  select *,
  case when kosho_seq = 1 then 1
        when APS_change = 1 then 1
        when keikabi > 90 then 2
        else 0 end as sai_flg
  from shoki_base3
  order by kosho_setteibi desc
)

select
hon.id as honkosho_id,
hon.anken_id,
an.kohosha_id,
tenki_id,
case when kohosha_ap_sql2.name is null then kohosha_ap_sql.name
     else kohosha_ap_sql2.name end as ap_source,
koho.birth_year,
koho.annual_income,
hon.kosho_setteibi as setteibi,
hon.kosho_yoteibi as yoteibi,
hon.kosho_jisshibi as jisshibi,
case when syi1.sei_plus is not null then syi1.sei_plus
     else hon.kohosha_tanto end as kohosha_tanto,
syi2.sei_plus as kigyo_tanto,
hon.kosho_seq as kaisu,
linked_shokikosho_id,
format_date('%Y/%m/%d',shoki.kosho_jisshibi) as shoki_jisshibi,
shoki.sai_flg,
yomi.name as first_yomi,
case when yomi2.name is null then yomi.name
     when yomi2.name = yomi.name then yomi2.name
     else yomi2.name end as last_yomi,
kgy.tsr_code,
kgy.name as company_name,
case when consts3.name is null then shoki.iseki_iyoku 
     else consts3.name end as iseki_iyoku,

-- kohosha_ap_sql.name as moto_apsource,
-- kohosha_sql.name as kohosha_rank,
-- kgy.name as company_name,
-- hon.kosho_seq_extra as absolute_1,
-- hon.kosho_jisshibi,
-- hon.mendan_tanto,
-- honkosho_kumite_sql.name as kumite_moto,
shoki.kosho_seq,
DATE_DIFF(hon.kosho_setteibi, shoki.kosho_jisshibi, DAY) as jisshibi_sa
from `r-group-bigdata.live_rhs.honkoshos` as hon
left join (select id,linked_shokikosho_id,kigyo_id,kohosha_id,kigyo_tanto,kumite 
           from `r-group-bigdata.live_rhs.ankens`) as an on hon.anken_id = an.id
left join (SELECT distinct anken_id, yomi
           FROM `r-group-bigdata.live_rhs.honkosho_yomis` where yomi = 100) yomis on an.id = yomis.anken_id
LEFT JOIN SHOKIS shoki on an.linked_shokikosho_id = shoki.id
left join (select id,seimei,ap_source,kohosha_rank,birth_year,annual_income,iseki_iyoku_new 
           from `r-group-bigdata.live_rhs.kohoshas`) as koho ON an.kohosha_id = koho.id
left join (select id,tsr_code,name 
           from `r-group-bigdata.live_rhs.kigyos`) as kgy on an.kigyo_id = kgy.id
left join (select group_code,code,name 
           from `r-group-bigdata.live_rhs.sys_consts` where group_code = 5200) as kohosha_sql ON koho.kohosha_rank = kohosha_sql.code
left join (select group_code,code,name 
           from `r-group-bigdata.live_rhs.sys_consts` where group_code = 19) as kohosha_ap_sql ON koho.ap_source = kohosha_ap_sql.code
left join (select group_code,code,name 
           from `r-group-bigdata.live_rhs.sys_consts` where group_code = 19) as kohosha_ap_sql2 ON shoki.ap_source = kohosha_ap_sql2.code
left join (select group_code,code,name 
           from `r-group-bigdata.live_rhs.sys_consts` where group_code = 4500) as honkosho_kumite_sql ON an.kumite = honkosho_kumite_sql.code
left join (SELECT code,name
           FROM `r-group-bigdata.live_rhs.sys_consts` where group_code = 9) yomi on hon.yomi = yomi.code
left join (SELECT code,name
           FROM `r-group-bigdata.live_rhs.sys_consts` where group_code = 9) yomi2 on yomis.yomi = yomi2.code
left join (SELECT code,name
           FROM `r-group-bigdata.live_rhs.sys_consts` where group_code = 5100) consts3 ON koho.iseki_iyoku_new = consts3.code
left join `r-group-bigdata.live_company.syain` syi1 on hon.kohosha_tanto = syi1.user_id
left join `r-group-bigdata.live_company.syain` syi2 on an.kigyo_tanto = syi2.user_id

)

select *,
  case when shoki_jisshibi is null then 2
       when jisshibi_sa > 90 then 2
       else sai_flg end as sai_flg2
from HONS
where 
-- kosho_setteibi >= '2017-04-01'
 ap_source = "転機社長名鑑"
and kaisu = 1
"""

rzhonkosho = client.query(rzhonkosho_query).result().to_dataframe()

# %%
adinfo["tenki_id"] = pd.to_numeric(adinfo["tenki_id"], errors='coerce')
adinfo["tenki_id"] = adinfo["tenki_id"].fillna(0)
adinfo["tenki_id"] = adinfo["tenki_id"].astype(int)
# rzhonkosho["tenki_id"] = rzhonkosho["tenki_id"].astype(str)


# %%
adinfo.dtypes

# %%
rzhonkosho = pd.merge(rzhonkosho,adinfo,on=("tenki_id"),how=("left"))

# %%
rzhonkosho.dtypes

# %%
rzhonkosho = rzhonkosho[["kohosha_id","anken_id","tenki_id","ap_source","birth_year","annual_income",
                         "登録日時","setteibi","yoteibi","jisshibi",
                         "kohosha_tanto","kigyo_tanto","kaisu","linked_shokikosho_id","shoki_jisshibi",
                         "sai_flg","first_yomi","last_yomi","tsr_code","company_name","iseki_iyoku","sai_flg2",
                         "参照元/メディア","キャンペーン","広告ID"]]
rzhonkosho['setteibi'] = pd.to_datetime(rzhonkosho['setteibi'])
filtered_data = rzhonkosho[rzhonkosho['setteibi'] >= '2019-09-30']

# %%
filtered_data
# filtered_data.to_excel('honkoshos.xlsx')


# %%
filtered_data["kohosha_id"] = filtered_data["kohosha_id"].astype(str) 
filtered_data["tenki_id"] = filtered_data["tenki_id"].astype(str).str.replace('<NA>', '') 
filtered_data["birth_year"] = filtered_data["birth_year"].astype(str).str.replace('<NA>', '') 
filtered_data["sai_flg"] = filtered_data["sai_flg"].astype(str).str.replace('<NA>', '') 

filtered_data["登録日時"] = filtered_data["登録日時"].astype(str).str.replace('NaN', '')
filtered_data["setteibi"] = filtered_data["setteibi"].astype(str) 
filtered_data["yoteibi"] = filtered_data["yoteibi"].astype(str)
filtered_data["jisshibi"] = filtered_data["jisshibi"].astype(str).str.replace('None', '')
filtered_data["shoki_jisshibi"] = filtered_data["shoki_jisshibi"].astype(str).str.replace('None', '')
filtered_data["iseki_iyoku"] = filtered_data["iseki_iyoku"].astype(str).str.replace('<NA>', '')

# %%
filtered_data

# %%

filtered_data.replace([np.inf, -np.inf], np.nan, inplace=True)
filtered_data.fillna('', inplace=True)

rzhonkosho_data = filtered_data.values.tolist()

# %%
#スプレッドシートに記載する
SPREADSHEET_ID = '1ofer5LQADQ9ppKrtQWWbOyhyEmcrBx_c_O4UmVFe3wU'
Sheet_NAME = '設定!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,rzhonkosho_data,service)

# %%
#スプレッドシートに記載する
SPREADSHEET_ID = '1qtTngN03WSZ_JjZovhNVh6bd1uc_Eh8tRP5Hp9yWSNc'
Sheet_NAME = 'settei!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,rzhonkosho_data,service)

# %% [markdown]
# ## SCKPI

# %%
sckpi_query = """
WITH
-- =================================================================
-- マスタデータ準備セクション
-- =================================================================

-- CTE 1: 四半期カレンダーのマスタデータ
calendar_master AS (
  SELECT
    yyyymmdd AS setting_date,
    CONCAT(ki, "-", q, "Q") AS Q
  FROM `r-group-bigdata.live_sugarcrm52.calendar_suka_master`
),

-- =================================================================
-- データ結合と基本加工セクション
-- =================================================================
base_data AS (
  SELECT
    rc.tenki_id,
    rc.age,
    can.ap_kakutoku AS shokikosho_setteibi,
    rc.first_nmen_date AS first_jisshi_date,
    can.nmen_zisshi AS shokikosho_jisshibi,
    -- COALESCE関数を使い、繰り返しが多いCASE文を簡潔に書き換え
    COALESCE(
      com.settei8, com.settei7, com.settei6, com.settei5,
      com.settei4, com.settei3, com.settei2, com.settei1
    ) AS honkosho_setteibi,
    COALESCE(
      com.zisshi8, com.zisshi7, com.zisshi6, com.zisshi5,
      com.zisshi4, com.zisshi3, com.zisshi2, com.zisshi1
    ) AS honkosho_jissibi,
    com.seiyaku,
    -- COALESCE関数を使い、担当者名の取得を簡潔に
    COALESCE(syi1.sei_plus, can.ap_kakutokusya_id) AS ap_kakutokusya,
    COALESCE(syi2.sei_plus, can.kouhosya_tantou_id) AS kohosha_tanto,
    COALESCE(syi4.sei_plus, can.mendan_tantou_id) AS mendan_tanto,
    COALESCE(syi3.sei_plus, can.client_tantou_id) AS kigyo_tanto,
    can.ap_source,
    cal.Q
  FROM
    `r-group-bigdata.live_sugarcrm52.rc_race_candidate_management` AS rc
    LEFT JOIN `r-group-bigdata.live_saltcrm.candidate` AS can ON can.sugarid = rc.candidate_no
    LEFT JOIN `r-group-bigdata.live_saltcrm.company` AS com ON com.candidate_id = can.id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON can.ap_kakutokusya_id = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON can.kouhosya_tantou_id = syi2.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi3 ON can.client_tantou_id = syi3.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi4 ON can.mendan_tantou_id = syi4.user_id
    LEFT JOIN calendar_master AS cal ON can.ap_kakutoku = cal.setting_date
  WHERE
    rc.tenki_id IS NOT NULL
    AND rc.deleted = 0
    AND can.ap_kakutoku >= DATE '2019-10-01'
)

-- =================================================================
-- 最終的な集計と出力
-- ウィンドウ関数を用いて登場回数フラグを付与する
-- =================================================================
SELECT
  *,
  -- tenki_idごとの登場回数を判定し、フラグを付与 (1: 初回, 2: 2回目以降)
  CASE
    WHEN ROW_NUMBER() OVER (PARTITION BY tenki_id ORDER BY shokikosho_setteibi, first_jisshi_date) = 1 THEN 1
    ELSE 2
  END AS occurrence_flag
FROM
  base_data
ORDER BY
  shokikosho_setteibi;


"""

sckpi = client.query(sckpi_query).result().to_dataframe()

# %%
teageinfo = teageinfo.rename(columns={"ID":"tenki_id"})
sckpi['tenki_id'] = sckpi['tenki_id'].astype(str)


sckpi_merged = pd.merge(sckpi,teageinfo,on=("tenki_id"),how=("left"))

# %%
sckpi_merged = sckpi_merged[["tenki_id","登録日時","フリ先","手あげ日付","担当",
                             "shokikosho_setteibi","first_jisshi_date","shokikosho_jisshibi","honkosho_setteibi","honkosho_jissibi","seiyaku",
                             "ap_kakutokusya","kohosha_tanto","mendan_tanto","kigyo_tanto","ap_source","KN共有日","age","occurrence_flag"]]

# %%
sckpi_merged["tenki_id"] = sckpi_merged["tenki_id"].astype(str).str.replace('<NA>', '') 
sckpi_merged["登録日時"] = sckpi_merged["登録日時"].astype(str).str.replace('NaN', '')
sckpi_merged["手あげ日付"] = sckpi_merged["手あげ日付"].astype(str).str.replace('None', '')
sckpi_merged["shokikosho_setteibi"] = sckpi_merged["shokikosho_setteibi"].astype(str).str.replace('None', '')
sckpi_merged["first_jisshi_date"] = sckpi_merged["first_jisshi_date"].astype(str).str.replace('None', '')
sckpi_merged["shokikosho_jisshibi"] = sckpi_merged["shokikosho_jisshibi"].astype(str).str.replace('None', '')
sckpi_merged["honkosho_setteibi"] = sckpi_merged["honkosho_setteibi"].astype(str).str.replace('None', '')
sckpi_merged["honkosho_jissibi"] = sckpi_merged["honkosho_jissibi"].astype(str).str.replace('None', '')
sckpi_merged["seiyaku"] = sckpi_merged["seiyaku"].astype(str).str.replace('None', '')
sckpi_merged["KN共有日"] = sckpi_merged["KN共有日"].astype(str).str.replace('None', '')
sckpi_merged["age"] = sckpi_merged["age"].astype(str).str.replace('<NA>', '') 

# %%
sckpi_merged.tail(10)

# %%

sckpi_merged.replace([np.inf, -np.inf], np.nan, inplace=True)
sckpi_merged.fillna('', inplace=True)

sckpi_final = sckpi_merged.values.tolist()

# %%
#スプレッドシートに記載する
SPREADSHEET_ID = '1ofer5LQADQ9ppKrtQWWbOyhyEmcrBx_c_O4UmVFe3wU'
Sheet_NAME = 'sckpi!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,sckpi_final,service)

# %% [markdown]
# ## 成約データ

# %%
# 過去ヨミ表のA~E列を取得
SPREADSHEET_ID = "1ITzx2eIAMpiepjGVrDSf-FR1XcAKzYJMqFZuS6-8qb0"
Sheet_NAME = 'data!'
Sheet_row = "A:E"
RANGE_NAME = Sheet_NAME+Sheet_row
yomi_old_betu = get_ss_optimized(SPREADSHEET_ID,RANGE_NAME,service)

yomi_old_betu = yomi_old_betu.rename(columns={"両手案件フラグ":"旧両手","アポソース丸め":"旧アポ",
                                                "候補者アポソース":"旧候補者アポ","候補者id":"旧候id"})

yomi_old_betu["発番"] = pd.to_numeric(yomi_old_betu["発番"], errors='coerce')

# %%
# 過去ヨミ表の情報を取得
SPREADSHEET_ID = "1ITzx2eIAMpiepjGVrDSf-FR1XcAKzYJMqFZuS6-8qb0"
Sheet_NAME = 'data!'
Sheet_row = "G:AV"
RANGE_NAME = Sheet_NAME+Sheet_row
yomi_old = get_ss_optimized(SPREADSHEET_ID,RANGE_NAME,service)

yomi_old = yomi_old.rename(columns={"営業売上\n（営業ポイント）.1":"営業売上\n（営業ポイント）"})


# %%
# 今QのRZヨミ表情報を取得
SPREADSHEET_ID = "1h8tyDhieP_gVp2Enj6dEJ3iR5yjyJzYNfLz1FH8U7r8"
Sheet_NAME = 'ヨミ表!'
Sheet_row = "A10:AZ4000"
RANGE_NAME = Sheet_NAME+Sheet_row
yomi_nowQ = get_ss_optimized(SPREADSHEET_ID,RANGE_NAME,service)

yomi_nowQ["計上日"] = pd.to_datetime(yomi_nowQ["計上日"])
yomi_nowQ["計上月"] = yomi_nowQ["計上日"].dt.month

yomi_nowQ["報酬率"] = pd.to_numeric(yomi_nowQ["報酬率"].str.replace('%', '', regex=False), errors='coerce').astype(float) / 100


# %%
#RPA事業部のクロスセルは除く(顧問名が「塩澤昌紘」はRPA事業部のクロスセル案件)
yomi_nowQ = yomi_nowQ[~yomi_nowQ['候補者'].isin(['塩澤昌紘'])]
yomi_nowQ = yomi_nowQ[~yomi_nowQ['売上種別（商品内容）'].isin(['RPAコンサル'])]
yomi_nowQ = yomi_nowQ[~yomi_nowQ['売上種別（商品内容）'].isin(['ビジネスタンク'])]
yomi_nowQ.to_excel('yomi_nowQ.xlsx')

yomi_nowQ["入力者"] = ""
yomi_nowQ["グループ企画料"] = ""
yomi_nowQ['引き継ぎP'] = ""
yomi_nowQ['特殊フラグ'] = ""
yomi_nowQ['備考①'] = ""
yomi_nowQ['備考②'] = ""
yomi_nowQ['備考③'] = ""
yomi_nowQ['担当'] = ""
yomi_nowQ['担当\n押印'] = ""
yomi_nowQ['d'] = ""
yomi_nowQ['d.1'] = ""
yomi_nowQ['アポソース'] = ""

yomi_nowQ = yomi_nowQ.rename(columns={
                                    #   '案件id （RZ）': '案件id\n（RZ）',
                                    #   '案件No （SC）':'案件\nNo\n（SC）',
                                      '完保成約割振比':'完保\n成約\n割振比','サービス引当係数':'サービス\n引当\n係数',
                                      'キャンセル引当係数':'キャンセル\n引当\n係数','査定用売上':'査定用\n売上',
                                      'シニアスカウト （ヨミ表と一致）':'シニアスカウト\n（ヨミ表と一致）',
                                      })

yomi_nowQ = yomi_nowQ[['案件id（RZ）','計上月', '期', '月','案件No（SC）','入力者','計上日','受注日',
                       'クライアント正式名称','候補者','売上種別（商品内容）','差分\n（該当場合のみ）',
                       '紹介引当/PM引当\n特殊ポイント\n（該当場合のみ）','基準年収', '報酬率', '完保\n成約\n割振比',"グループ企画料",
                       'サービス\n引当\n係数', 'キャンセル\n引当\n係数','営業売上合計', '所属課', '氏名','割合', '受注額',
                       '査定用\n売上','顧客支持ポイント', '引き継ぎP','担当', '担当\n押印', '備考①', '備考②', '備考③',
                       'シニアスカウト\n（ヨミ表と一致）', '内定数フラグ','企業アポソース','特殊フラグ','提示/前年度','基準年収.1',
                       '報酬率.1', 'd', 'd.1', 'アポソース']]


# %%
# 列名の重複を削除する処理を追加（重複がある場合は最初の列を残します）
yomi_old = yomi_old.loc[:, ~yomi_old.columns.duplicated()]
yomi_nowQ = yomi_nowQ.loc[:, ~yomi_nowQ.columns.duplicated()]

# 過去計上済のヨミ表情報と、今Qのヨミ表とをくっつける
yomi = pd.concat([yomi_old, yomi_nowQ], axis=0, ignore_index=True)

# %%
rzhonkosho

rzhonkosho.to_excel('rzhonkosho.xlsx')

rzhonkosho_date = rzhonkosho.copy()

# %%
rzhonkosho_date.sample(10)

# %%
rzhonkosho_date["age"] = rzhonkosho_date["setteibi"].dt.year.astype('int64')-rzhonkosho_date["birth_year"]
rzhonkosho_date = rzhonkosho_date[["kohosha_id","anken_id","tenki_id","ap_source","登録日時","setteibi","yoteibi","jisshibi","kohosha_tanto","kigyo_tanto","age","annual_income","sai_flg2","linked_shokikosho_id","shoki_jisshibi"]]
rzhonkosho_date = rzhonkosho_date.drop_duplicates(subset=["anken_id","tenki_id","ap_source","登録日時","setteibi","yoteibi","jisshibi","kohosha_tanto","kigyo_tanto","sai_flg2"])


# %%
yomi_work = yomi[["案件id（RZ）","計上月","期","月","案件No（SC）","計上日","受注日","クライアント正式名称","候補者","売上種別（商品内容）","基準年収",
                       "報酬率","営業売上合計","所属課","氏名","顧客支持ポイント","基準年収.1","アポソース"]]
yomi_work = yomi_work.rename(columns={"案件id（RZ）":"anken_id"})
yomi_work = yomi_work.drop_duplicates(subset=["anken_id","計上月","期","月","案件No（SC）","計上日","受注日","クライアント正式名称","候補者","売上種別（商品内容）","基準年収",
                       "報酬率","営業売上合計","所属課","氏名","顧客支持ポイント","基準年収.1","アポソース"])
yomi_work.to_excel('yomi_work.xlsx')


# %%
yomi_work['anken_id'] = pd.to_numeric(yomi_work['anken_id'], errors='coerce').astype('Int64')

# %%

merged_data = pd.merge(yomi_work, rzhonkosho_date, on='anken_id', how='left')
merged_data["部署"] = "ロンザン"

# %%
display(yomi_work.dtypes)
display(rzhonkosho_date.dtypes)

# %%
merged_data = merged_data[["tenki_id","anken_id","登録日時","部署","計上日","受注日","age","annual_income","kohosha_id","営業売上合計",
                           "顧客支持ポイント","基準年収","linked_shokikosho_id","shoki_jisshibi","setteibi","yoteibi","jisshibi","kohosha_tanto","kigyo_tanto","sai_flg2","所属課","ap_source"]]

# %%
merged_data = merged_data[(merged_data['所属課'] == '外部原価') & (merged_data['ap_source'].str.contains('転機社長名鑑'))]
merged_data = merged_data[["tenki_id","anken_id","登録日時","部署","計上日","受注日","age","annual_income","kohosha_id","営業売上合計",
                           "顧客支持ポイント","基準年収","linked_shokikosho_id","shoki_jisshibi","setteibi","yoteibi","jisshibi","kohosha_tanto","kigyo_tanto","sai_flg2"]]


# %%
merged_data["tenki_id"] = merged_data["tenki_id"].astype(str) .str.replace('<NA>', '-')
merged_data["anken_id"] = merged_data["anken_id"].astype(str)
merged_data["登録日時"] = merged_data["登録日時"].astype(str).str.replace('nan', '-')

merged_data["linked_shokikosho_id"] = merged_data["linked_shokikosho_id"].astype(str)
merged_data['計上日'] = pd.to_datetime(merged_data['計上日'], errors='coerce')
merged_data['計上日'] = merged_data['計上日'].dt.strftime('%Y/%m/%d')
merged_data['受注日'] = pd.to_datetime(merged_data['受注日'], errors='coerce')
merged_data['受注日'] = merged_data['受注日'].dt.strftime('%Y/%m/%d')
merged_data["age"] = merged_data["age"].astype(str)
merged_data["setteibi"] = merged_data['setteibi'].dt.strftime('%Y/%m/%d')
merged_data["annual_income"] = merged_data["annual_income"].astype(str)
merged_data["kohosha_id"] = merged_data["kohosha_id"].astype(str) 

merged_data['営業売上合計'] = merged_data['営業売上合計'].astype(str)
merged_data['顧客支持ポイント'] = merged_data['顧客支持ポイント'].astype(str)
merged_data['基準年収'] = merged_data['基準年収'].astype(str)
merged_data['sai_flg2'] = merged_data['sai_flg2'].astype(str)

# %%
merged_data
merged_data.to_excel('merged_data.xlsx')


# %% [markdown]
# ## SC成約データ

# %%
#過去のポイントデータは過去ヨミ表を集約したデータからとってくる
sc_yomi_kakoQ = pd.read_excel(r"\\172.16.0.232\CoffeeCrazy\経営ソリューション事業部\□シニアスカウト事業部□\01 全体進捗\02 行動カレンダー\pythonデータ\yojitu\SCpoint.xlsx",header=0,usecols = (range(0, 43)))



# %%
# 今Qレイノスのヨミ表の情報を取得
SPREADSHEET_ID = "1ernZCIU-9qEx6Xg9TzYkGSvmDmbE0ct-sE-Zpm0HSM4"
Sheet_NAME = 'ヨミ表!'
Sheet_row = "A10:AV"
RANGE_NAME = Sheet_NAME+Sheet_row
sc_yomi_now = get_ss_optimized(SPREADSHEET_ID,RANGE_NAME,service)

# %%
temp_datetime = pd.to_datetime(sc_yomi_now['月'], format='%Y年%m月', errors='coerce')

month_series = temp_datetime.dt.month
sc_yomi_now['計上月'] = month_series.apply(lambda x: f"{int(x)}月" if pd.notna(x) else "")




# %%
sc_yomi_now = sc_yomi_now.rename(columns={'差分（該当場合のみ）':'差分\n（該当場合のみ）',
                                          '売上種別 （商品内容）':'売上種別（商品内容）',
                                          '報酬率':'・報酬率\n（スカウト報酬）\n・原価（新卒）',
                                          '完保成約割振比': '完保\n成約\n割振比','営業売上合計':'営業\n売上\n合計','査定用売上':'査定用\n売上'})

sc_yomi_now['入力者'] = ""
sc_yomi_now['紹介引当/PM引当\n特殊ポイント\n（該当場合のみ）'] = ""
sc_yomi_now['新ポイント用'] = ""
sc_yomi_now['引き継ぎP'] = ""
sc_yomi_now['特別戻り顧客支持ポイント'] = ""
sc_yomi_now['担当\n押印'] = ""
sc_yomi_now['備考①'] = ""
sc_yomi_now['備考②'] = ""
sc_yomi_now['備考③'] = ""
sc_yomi_now['修正フラグ'] = ""
sc_yomi_now[ 'クロスセルフラグ'] = ""
sc_yomi_now['Unnamed: 32'] = ""
sc_yomi_now[' '] = ""
sc_yomi_now['Unnamed: 34'] = ""
sc_yomi_now['Unnamed: 35'] = ""
sc_yomi_now['Unnamed: 36'] = ""
sc_yomi_now['ポイントID'] = ""
sc_yomi_now['アポソース'] = ""
sc_yomi_now['パートナー紹介'] = ""
sc_yomi_now['Unnamed: 40'] = ""
sc_yomi_now['category1'] = ""
sc_yomi_now['category2'] = ""

sc_yomi_now = sc_yomi_now[['計上月','期', '月','案件No','入力者', '計上日', 'クライアント正式名称', '候補者',
                            '売上種別（商品内容）', '差分\n（該当場合のみ）','紹介引当/PM引当\n特殊ポイント\n（該当場合のみ）',
                            '基準年収',
                            '・報酬率\n（スカウト報酬）\n・原価（新卒）', '完保\n成約\n割振比','新ポイント用', 'CS・CXL引当','外部原価',
                            '営業\n売上\n合計','所属課', '氏名','割合','受注額','査定用\n売上','顧客支持ポイント','引き継ぎP',
                            '特別戻り顧客支持ポイント','担当\n押印', '備考①', '備考②', '備考③', '修正フラグ', 'クロスセルフラグ',
                            'Unnamed: 32', ' ', 'Unnamed: 34', 'Unnamed: 35', 'Unnamed: 36',
                            'ポイントID', 'アポソース', 'パートナー紹介', 'Unnamed: 40', 'category1', 'category2'
                            ]]

sc_yomi_now = sc_yomi_now.rename(columns={'計上日': '受注日'})

sc_yomi_now['期'] = pd.to_numeric(sc_yomi_now['期'], errors='coerce').fillna(0).astype('int64')
sc_yomi_now['月'] = sc_yomi_now['月'].str.extract(r'(\d+)月').astype(float).astype('Int64')
sc_yomi_now['基準年収'] = pd.to_numeric(sc_yomi_now['基準年収'], errors='coerce').fillna(0).astype('int64')
sc_yomi_now['案件No'] = pd.to_numeric(sc_yomi_now['案件No'], errors='coerce').fillna(0).astype('int64')
sc_yomi_now['受注額'] = pd.to_numeric(sc_yomi_now['受注額'], errors='coerce').fillna(0).astype('int64')
sc_yomi_now['顧客支持ポイント'] = pd.to_numeric(sc_yomi_now['顧客支持ポイント'], errors='coerce').fillna(0).astype('int64')
sc_yomi_now['受注日'] = pd.to_datetime(sc_yomi_now['受注日'], errors='coerce')



# %%


# %%
sc_yomi = pd.concat([sc_yomi_kakoQ, sc_yomi_now], axis=0, ignore_index=True, join='outer')

# %%
# 外部原価が"外部原価"かつ 氏名が"転機"の条件を追加
sc_yomi = sc_yomi[
    (sc_yomi["所属課"].isin(["外部原価", "PDM引当", ""])) & 
    (sc_yomi["氏名"] == "転機")]
sc_yomi = sc_yomi[["計上月","期","月","案件No","クライアント正式名称","候補者","受注日",
                   "基準年収","売上種別（商品内容）","営業\n売上\n合計",
                   "所属課","氏名","受注額","顧客支持ポイント","アポソース"]]

import re
# 候補者から半角・全角スペースと「氏」を除去して詰めた状態で出力
def process_candidate_name(name):
    # 半角と全角空白を取り除き、「氏」を除去
    cleaned_name = re.sub(r'[　\s]*氏[　\s]*', '', name)  # 「氏」を取り除く
    cleaned_name = cleaned_name.replace(' ', '')           # 半角スペースを取り除く
    cleaned_name = cleaned_name.replace('　', '')          # 全角スペースを取り除く
    return cleaned_name

# 列に適用
sc_yomi['候補者'] = sc_yomi['候補者'].apply(process_candidate_name)
sc_yomi = sc_yomi.rename(columns={"クライアント正式名称":"client_name","候補者":"kohosya_name"})


# %%
sc_yomi

# %%
sc_yomi.to_excel('sc_yomi_data.xlsx')

# %%
# 同じclient_nameとkohosya_nameでグループ化し、顧客支持ポイントを合算
# result = sc_yomi.groupby(['client_name', 'kohosya_name','受注日','基準年収'], as_index=False).agg({'営業\n売上\n合計': 'sum','顧客支持ポイント': 'sum'})

result = sc_yomi.groupby(['案件No', 'client_name', 'kohosya_name', '受注日', '基準年収'], as_index=False).agg({
    '営業\n売上\n合計': 'sum',
    '顧客支持ポイント': 'sum'
})

# %%
result

# %%
# result.to_excel('scyomi_result.xlsx')

# %%
result = result.rename(columns={"受注日":"計上日","営業\n売上\n合計":"営業売上合計"})
result["部署"] = "レイノス"
result["受注日"] = ""
result = result[["案件No","client_name","kohosya_name","計上日","受注日","基準年収","営業売上合計","顧客支持ポイント"]]
result = result.sort_values(by='計上日')

# %%
result

# %%
sckpi_query = """
WITH
-- =================================================================
-- データ結合と基本加工セクション
-- 必要なテーブルを結合し、基本的なカラムを計算する
-- =================================================================
base_data AS (
  SELECT
    rc.tenki_id,
    can.ap_kakutoku AS shokikosho_setteibi,
    rc.first_nmen_date AS first_jisshi_date,
    can.nmen_zisshi AS shokikosho_jisshibi,
    COALESCE(
      com.settei8, com.settei7, com.settei6, com.settei5,
      com.settei4, com.settei3, com.settei2, com.settei1
    ) AS honkosho_setteibi,
    COALESCE(
      com.zisshi8, com.zisshi7, com.zisshi6, com.zisshi5,
      com.zisshi4, com.zisshi3, com.zisshi2, com.zisshi1
    ) AS honkosho_jissibi,
    com.seiyaku,
    can.kouhosya_tantou AS kohosha_tanto,
    com.client_name,

    -- 【妙案ポイント1】フルネームから正規表現で「最初のスペースより前（名字）」だけを抽出
    REGEXP_EXTRACT(com.kouhosya_name, r'^([^ \s ]+)') AS kohosya_name,
    
    -- 【妙案ポイント2】案件Noに該当する sc_project_id を取得
    com.sc_project_id,

    rc.age,
    can.client_tantou AS kigyo_tanto,
    can.mendan_tantou AS mendan_tanto,
    com.moto_ap_source,
    com.ap_source,
    CASE
      WHEN can.zisshi LIKE 'キャンセル%' THEN 'CXL'
      WHEN can.zisshi LIKE '%実施%' THEN '実施'
      ELSE '-'
    END AS CXL_status
  FROM
    `r-group-bigdata.live_sugarcrm52.rc_race_candidate_management` AS rc
    LEFT JOIN `r-group-bigdata.live_saltcrm.candidate` AS can ON can.sugarid = rc.candidate_no
    LEFT JOIN `r-group-bigdata.live_saltcrm.company` AS com ON com.candidate_id = can.id
  WHERE
    rc.tenki_id IS NOT NULL
    AND rc.deleted = 0
),

Final as (
-- =================================================================
-- 最終的な集計と出力
-- ウィンドウ関数を用いて登場回数をカウントする
-- =================================================================
SELECT
  *,
  -- tenki_idごとに、shokikosho_setteibi（設定日）の昇順で登場回数をカウント
  ROW_NUMBER() OVER (PARTITION BY tenki_id ORDER BY shokikosho_setteibi) AS sai_flg2
FROM
  base_data
where shokikosho_setteibi >= DATE '2019-10-01'
ORDER BY
  shokikosho_setteibi)

select *
from Final
where seiyaku is not null
and (moto_ap_source = "転機" or ap_source = "転機" or ap_source = "マッチング" or ap_source = "再")

"""

sckpi = client.query(sckpi_query).result().to_dataframe()



# %%
# sckpi.to_excel('sckpi.xlsx')

# %%


# %%
# 念のため、結合キーとなる「案件No」の型を文字列(str)で揃えておきます
result['案件No'] = result['案件No'].astype(str)
sckpi['sc_project_id'] = sckpi['sc_project_id'].astype(str)

# sckpi側のカラム名 'sc_project_id' を、result側の '案件No' に合わせて変更します
sckpi = sckpi.rename(columns={'sc_project_id': '案件No'})

# 【妙案ポイント3】3つのキーを配列（リスト）で指定して安全に結合します
# combined_keyを作らなくても、on=[キー1, キー2, キー3] と書くだけで複数条件のマージが可能です！
merged_scyomi = pd.merge(
    result,
    sckpi,
    on=['案件No', 'client_name', 'kohosya_name'], 
    how='left'
)

# 以下は元の処理のままです
merged_scyomi["tenki_id"] = merged_scyomi["tenki_id"].astype(str)
merged_scyomi = pd.merge(merged_scyomi, teageinfo, on="tenki_id", how="left")

# %%
merged_scyomi.head(5)


# %%
merged_scyomi["部署"] = "レイノス"
merged_scyomi["annual_income"] = ""
merged_scyomi["kohosha_id"] = ""
merged_scyomi["基準年収"] = ""
merged_scyomi["linked_shokikosho_id"] = ""
merged_scyomi["yoteibi"] = ""
merged_scyomi["kohosha_tanto"] = ""
merged_scyomi["kigyo_tanto"] = ""


# %%
merged_scyomi = merged_scyomi.rename(columns={"案件No":"anken_id"})

merged_scyomi = merged_scyomi[["tenki_id","anken_id","登録日時","部署","計上日","受注日","age","annual_income","kohosha_id","営業売上合計","顧客支持ポイント",
                  "基準年収","linked_shokikosho_id","shokikosho_jisshibi","honkosho_setteibi","yoteibi","honkosho_jissibi","kohosha_tanto","kigyo_tanto","sai_flg2"]]

# %%
merged_scyomi = merged_scyomi.rename(columns={"linked_shokikosho_id":"shoki_jisshibi","honkosho_setteibi":"setteibi","honkosho_jissibi":"jisshibi"})

# %%
# merged_dataとmerged_scyomiを結合
merged_result = pd.concat([merged_data.reset_index(drop=True), merged_scyomi.reset_index(drop=True)], ignore_index=True)

# '計上日' 列を日付型に変換
merged_result['計上日'] = pd.to_datetime(merged_result['計上日'], errors='coerce')

# データフレームを計上日でソート
merged_sorted = merged_result.sort_values(by='計上日', ascending=True, na_position='last')

# %%
merged_sorted.to_excel('merged_sorted.xlsx')

# %%
merged_data

# %%
import pandas as pd
import numpy as np

# date_columnsに空文字の代わりにNaNを設定
date_columns = ['計上日', '受注日', 'setteibi', 'yoteibi', 'jisshibi']
for col in date_columns:
    if col in merged_sorted.columns:
        # 空文字をNaNに置換
        merged_sorted[col] = merged_sorted[col].where(merged_sorted[col] != '', np.nan)
        # NaTに変換
        merged_sorted[col] = pd.to_datetime(merged_sorted[col], errors='coerce')
        # フォーマットしてNaTを'-'に置き換え
        merged_sorted[col] = merged_sorted[col].dt.strftime('%Y/%m/%d').fillna('-')

# 数値列にはゼロや適切な値を使う
numeric_columns = merged_sorted.select_dtypes(include=['int64', 'float64']).columns
for col in numeric_columns:
    merged_sorted[col] = merged_sorted[col].fillna(0)  # NaNをゼロで埋める

# 残りのオブジェクト型列を空文字で埋める
for col in merged_sorted.columns:
    if col not in date_columns and col not in numeric_columns:
        if merged_sorted[col].dtype == 'object':  # オブジェクト型であることを確認
            merged_sorted[col] = merged_sorted[col].fillna("")  # NaNを空文字で埋める

# Copyを行うが、強制的に中身をコピーするだけの目的のためのもの
merged_sorted = merged_sorted.copy()


# %%
merged_sorted

# %%
merged_sorted.drop(columns=['shokikosho_jisshibi'], inplace=True)

# %%
merged_sorted

# %%
import pandas as pd
import numpy as np

# merged_sortedの内容を確認
if merged_sorted is None:
    raise ValueError("merged_sorted is None. Please check the data loading or merging process.")

# 'NaN'と無限大を処理する
merged_sorted.replace([np.inf, -np.inf], np.nan, inplace=True)

# 空文字をNaNに置換し、日付型に変換したい列を処理
date_columns = ['計上日', '受注日', 'setteibi', 'yoteibi', 'jisshibi']
for col in date_columns:
    if col in merged_sorted.columns:
        # 空文字をNaNに置換
        merged_sorted[col].replace('', np.nan, inplace=True)
        # 日付型に変換
        merged_sorted[col] = pd.to_datetime(merged_sorted[col], errors='coerce')

# NaNを適切な値に置換
for col in merged_sorted.columns:
    if col in date_columns:
        merged_sorted[col].fillna('-', inplace=True)
    elif merged_sorted[col].dtype in ['int64', 'float64']:
        merged_sorted[col].fillna(0, inplace=True)
    else:
        if merged_sorted[col].dtype == 'object':
            merged_sorted[col].fillna("", inplace=True)

# リストに変換
yomi_data = merged_sorted.values.tolist()

# 各要素を文字列化
yomi_data = [[str(item) if not isinstance(item, str) else item for item in row] for row in yomi_data]


# %%
merged_sorted

# %%
#スプレッドシートに記載する
SPREADSHEET_ID = '1ofer5LQADQ9ppKrtQWWbOyhyEmcrBx_c_O4UmVFe3wU'
Sheet_NAME = 'yomihyo!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,yomi_data,service)

# %%
#スプレッドシートに記載する
SPREADSHEET_ID = '1qtTngN03WSZ_JjZovhNVh6bd1uc_Eh8tRP5Hp9yWSNc'
Sheet_NAME = 'yomihyo!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,yomi_data,service)

# %%



