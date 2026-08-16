# %%
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

client = bigquery.Client(credentials=credentials, project=credentials.project_id)


# %%
def to_str_columns(df, columns, clean_value=None):
    for col in columns:
        series = df[col].astype(str)
        if clean_value is not None:
            series = series.str.replace(clean_value, '', regex=False)
        df[col] = series
    return df

def merge_kigyo_tanto_attrs(df):
    df = pd.merge(df, kigyo_tanto_shokushu, on=("Q", "kigyo_tanto"), how="left")
    df = pd.merge(df, kigyo_tanto_layer, on=("Q", "kigyo_tanto"), how="left")
    df = pd.merge(df, kigyo_tanto_nenji, on=("Q", "kigyo_tanto"), how="left")
    return df


# %%
pd.set_option('display.max_rows', 100)
pd.set_option('display.max_columns', None)

# %%
#カレンダー情報
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly',
          'https://www.googleapis.com/auth/spreadsheets']
json_path = r"Z:\Users\suehara\Documents\python\analysis\python_ss\credentials.json"
service = ps.get_auth(SCOPES,json_path)
SPREADSHEET_ID = '1Gpbg3cMCFGNt4dJ0xfVZJmJfV_l_B9V6IM2QKDK8qoc'
Sheet_NAME = 'Q営業日!A'
Sheet_row = ":K"
RANGE_NAME = Sheet_NAME+Sheet_row
calendar = ps.get_ss(SPREADSHEET_ID,RANGE_NAME,service)
calendar = calendar[["日付","Q","同営業日比較"]]
calendar['日付'] = pd.to_datetime(calendar['日付'])
calendar = calendar.rename(columns={"日付":"appoint_get_date"})
calendar

# %%
calendar.dtypes

# %%
#ロンザンメンバ‐情報
SPREADSHEET_ID = '1ULtRmgKopKne9EYf8SEkQlO9oPCviincWqFCtAgXFCA'
Sheet_NAME = '職種推移!A'
Sheet_row = ":I"
RANGE_NAME = Sheet_NAME+Sheet_row
rzmember = ps.get_ss(SPREADSHEET_ID,RANGE_NAME,service)
rzmember = rzmember[["Q","略氏名","レイヤー","職種","年次"]]

kakutoku_shokushu = rzmember.rename(columns={"略氏名":"ap_kakutokusha","職種":"AP獲得職種"})
kakutoku_shokushu = kakutoku_shokushu[["Q","ap_kakutokusha","AP獲得職種"]]
kakutoku_layer = rzmember.rename(columns={"略氏名":"ap_kakutokusha","レイヤー":"AP獲得レイヤー"})
kakutoku_layer = kakutoku_layer[["Q","ap_kakutokusha","AP獲得レイヤー"]]
kakutoku_nenji = rzmember.rename(columns={"略氏名":"ap_kakutokusha","年次":"AP獲得年次"})
kakutoku_nenji = kakutoku_nenji[["Q","ap_kakutokusha","AP獲得年次"]]

homon_shokushu = kakutoku_shokushu.rename(columns={"ap_kakutokusha":"ap_homonsha","AP獲得職種":"訪問職種"})
homon_layer = kakutoku_layer.rename(columns={"ap_kakutokusha":"ap_homonsha","AP獲得レイヤー":"訪問レイヤー"})
homon_nenji = kakutoku_nenji.rename(columns={"ap_kakutokusha":"ap_homonsha","AP獲得年次":"訪問年次"})

kigyo_tanto_shokushu = kakutoku_shokushu.rename(columns={"ap_kakutokusha":"kigyo_tanto","AP獲得職種":"企担：職種"})
kigyo_tanto_layer = kakutoku_layer.rename(columns={"ap_kakutokusha":"kigyo_tanto","AP獲得レイヤー":"企担：レイヤー"})
kigyo_tanto_nenji = kakutoku_nenji.rename(columns={"ap_kakutokusha":"kigyo_tanto","AP獲得年次":"企担：年次"})


# %%
rzmember
kakutoku_shokushu
kakutoku_layer
kakutoku_nenji

# %% [markdown]
# ## 営業データ

# %%
sales_data_query = """
WITH 
-- ▼▼▼ 修正: pjテーブルを経由し、確実なIDでクライアントのTSR_CODEを取得 ▼▼▼
contract_history_base AS (
  SELECT
    cli.tsr_code AS tsr_code,
    CAST(ge.seiyaku_date AS DATE) AS yomi_torokubi
  FROM `r-group-bigdata.live_sugarcrm52.geppou_naitei_temp` ge
  LEFT JOIN `r-group-bigdata.live_spms.sc_projects` pj ON ge.project_no = pj.id
  LEFT JOIN `r-group-bigdata.live_spms.clients` cli ON pj.client_id = cli.id
  WHERE ge.scout_category LIKE "%ロンザン%"
    AND ge.seiyaku_date IS NOT NULL
),

-- ▼▼▼ 既存: 取得した成約日を企業(tsr_code)ごとに最新順のリスト(配列)にまとめる ▼▼▼
contract_history_arr AS (
  SELECT
    tsr_code,
    ARRAY_AGG(yomi_torokubi IGNORE NULLS ORDER BY yomi_torokubi DESC) AS contract_dates
  FROM contract_history_base
  WHERE tsr_code IS NOT NULL
  GROUP BY tsr_code
),

-- ▼▼▼ 既存: salesap_raw (削除データはここで除外) ▼▼▼
salesap_raw_base AS (
  SELECT 
      ap.id as ap_id,
      ap.tsr_code,
      ap.company_name,
      case when syi1.sei_plus is null then ap.appoint_get_syain 
           else syi1.sei_plus end as ap_kakutokusha,
      ap.appoint_visit_syain,
      syi2.sei_plus as ap_homonsha,
      ap.appoint_get_date,
      ap.appoint_visit_plan_date,
      ful.fulfills_date as jisshibi,
      case when consts.name like "%源泉%" then "源泉"
           when consts.name like "%RZ管S%" then "ロンザン管S"          
           when consts.name like "%RZ現S%" then "ロンザン現S"
           when consts.name like "%RZ元S%" then "ロンザン元S"
           when consts.name like "%スカウト現S%" then "スカウト現元S"
           when consts.name like "%スカウト元S%" then "スカウト現元S"
           when consts.name like "%顧問現S%" then "他部署現元S"
           when consts.name like "%顧問元S%" then "他部署現元S"
           when consts.name like "%プロ時短現S%" then "他部署現元S"
           when consts.name like "%プロ時短元S%" then "他部署現元S"
           when consts.name like "%他部署現S%" then "他部署現元S"
           when consts.name like "%他部署元S%" then "他部署現元S"
           when consts.name like "%他部署管S%" then "他部署管S"
           when consts.name like "%顧問管S%" then "他部署管S"
           when consts.name like "%スカウト管S%" then "他部署管S"
           else "その他" end as AP_source,
      shuho.name as shuho,
      ap.visit_times,
      tsr.race_owner,
      REGEXP_EXTRACT(tsr.address, r'^.{2,3}[都道府県]') AS prefecture,
      ap.appoint_visit_client_position,
      ROUND(tokikessan_uriagedaka/100000,0)as TOKI_URIAGE,
      LEFT(tsr.establishment,4) as setsuritsu,
      ROUND(maemaekikessan_uriagedaka/100000,0) as zenzenki_uriage,
      ROUND(zenkikessan_uriagedaka/100000,0) as zenki_uriage,
      ROUND(tokikessan_uriagedaka/100000,0) as konki_uriage,
      ROUND(maemaekikessan_riekikin/100000,1) as zenzenki_rieki,
      ROUND(zenkikessan_riekikin/100000,1) as zenki_rieki,
      ROUND(tokikessan_riekikin/100000,1) as konki_rieki,
      LEFT(tokikessan_kessantoshitsuki,4) as toshi,
      RIGHT(tokikessan_kessantoshitsuki,2) as tsuki,
      tsr.industry1,
      tsr.employee_num,
      ful.price_explanation3 as price,
      case
       when UPPER(appoint_visit_client_address) like '%ZOOM%' then 'ZOOM'
       else appoint_visit_client_address end as appoint_visit_client_address,
      cal.q,
      case when ap.deleted = 1 then "削除"
           when ap.deleted = 2 then "CXL"
           when ful.fulfills_date is null and ap.cxl_oikaden is not null then "CXL"
           when ful.fulfills_date is not null then sales_results.name
           else "未報告" end as CXL,
      sales_results.name as result_status,
      ROW_NUMBER() OVER (PARTITION BY ap.company_name,cal.q ORDER BY ap.appoint_get_date asc) as rn
  FROM `r-group-bigdata.live_rhs.sales_appoints` ap
  left join `r-group-bigdata.live_rhs.sales_appoint_fulfills` ful on ap.id = ful.id 
  left join `r-group-bigdata.tsr.company_info` tsr on ap.tsr_code = tsr.tsr_code 
  LEFT JOIN `r-group-bigdata.live_company.syain` syi1 on ap.appoint_get_syain = syi1.user_id
  LEFT JOIN `r-group-bigdata.live_company.syain` syi2 on ap.appoint_visit_syain = syi2.user_id
  LEFT JOIN (SELECT code,name FROM `r-group-bigdata.live_rhs.sys_consts` where group_code = 110) consts on cast(ap.appoint_source as int) = consts.code 
  LEFT JOIN (SELECT code,name FROM `r-group-bigdata.live_rhs.sys_consts` where group_code = 5500) shuho on cast(ap.shuho as int) = shuho.code
  LEFT JOIN (SELECT code,name FROM `r-group-bigdata.live_rhs.sys_consts` where group_code = 32) sales_results on cast(ful.result_status as int) = sales_results.code
  LEFT JOIN (SELECT yyyymmdd as date, concat(ki,"-",q,"Q") as Q FROM `r-group-bigdata.live_sugarcrm52.calendar_suka_master`) cal on ap.appoint_visit_plan_date = cal.date
),
salesap_raw AS (
  SELECT * FROM salesap_raw_base WHERE CXL != '削除'
),

-- ▼▼▼ 追加: 実績結合 ＆ 企業単位での履歴の取得 ▼▼▼
salesap_history_prep AS (
  SELECT
    ap.*,
    (
      SELECT c_date FROM UNNEST(ch.contract_dates) AS c_date 
      WHERE c_date <= CAST(ap.appoint_get_date AS DATE) 
      ORDER BY c_date DESC LIMIT 1
    ) AS last_contract_date,
    
    LAG(ap.CXL) OVER (
      PARTITION BY ap.tsr_code ORDER BY ap.appoint_get_date ASC, ap.ap_id ASC
    ) AS prev_cxl,
    LAG(ap.appoint_visit_plan_date) OVER (
      PARTITION BY ap.tsr_code ORDER BY ap.appoint_get_date ASC, ap.ap_id ASC
    ) AS true_prev_visit_plan_date

  FROM salesap_raw ap
  LEFT JOIN contract_history_arr ch ON ap.tsr_code = ch.tsr_code
),

-- ▼▼▼ 追加: 「管S」への状態遷移の判定 ▼▼▼
salesap_state_calc AS (
  SELECT
    *,
    CASE 
      WHEN prev_cxl = '未報告' THEN 1 
      WHEN prev_cxl NOT IN ('CXL', '未報告') 
           AND DATE_DIFF(CAST(appoint_get_date AS DATE), CAST(true_prev_visit_plan_date AS DATE), DAY) > 90 THEN 1 
      ELSE 0 
    END AS is_trigger_kans
  FROM salesap_history_prep
),
salesap_true_source_prep AS (
  SELECT
    *,
    MAX(is_trigger_kans) OVER (
      PARTITION BY tsr_code ORDER BY appoint_get_date ASC, ap_id ASC
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS is_kans_mode
  FROM salesap_state_calc
),

-- ▼▼▼ 追加: 【真のAPソース】の決定 ▼▼▼
salesap_with_true_source AS (
  SELECT
    *,
    CASE
      WHEN AP_source IN ('スカウト現元S', '他部署現元S', '他部署管S') THEN AP_source
      WHEN last_contract_date IS NOT NULL AND DATE_DIFF(CAST(appoint_get_date AS DATE), last_contract_date, DAY) <= 365 THEN 'ロンザン現S'
      WHEN last_contract_date IS NOT NULL AND DATE_DIFF(CAST(appoint_get_date AS DATE), last_contract_date, DAY) > 365 THEN 'ロンザン元S'
      WHEN is_kans_mode > 0 THEN 'ロンザン管S'
      WHEN prev_cxl IS NULL THEN '源泉'
      WHEN prev_cxl = 'CXL' THEN '源泉'
      WHEN prev_cxl NOT IN ('CXL', '未報告') AND DATE_DIFF(CAST(appoint_get_date AS DATE), CAST(true_prev_visit_plan_date AS DATE), DAY) <= 90 THEN '再訪'
      ELSE '源泉'
    END AS true_ap_source
  FROM salesap_true_source_prep
),

-- ▼▼▼ 既存ステップ1: 担当者別の前回訪問予定日を取得（価格埋め用） ▼▼▼
salesap_with_prev as (
  SELECT
    *,
    LAG(appoint_visit_plan_date) OVER (
      PARTITION BY tsr_code, appoint_visit_syain 
      ORDER BY appoint_visit_plan_date ASC, ap_id ASC
    ) as prev_visit_plan_date
  FROM salesap_with_true_source
),

-- ▼▼▼ 既存ステップ2: 90日ルールでセッションIDを付与 ▼▼▼
salesap_with_session as (
  SELECT
    *,
    SUM(CASE 
          WHEN prev_visit_plan_date IS NULL THEN 0 
          WHEN DATE_DIFF(appoint_get_date, prev_visit_plan_date, DAY) > 90 THEN 1 
          ELSE 0 
        END) OVER (
          PARTITION BY tsr_code, appoint_visit_syain 
          ORDER BY appoint_visit_plan_date ASC, ap_id ASC
        ) as session_id
  FROM salesap_with_prev
),

-- ▼▼▼ 既存ステップ3: セッション内で未来の価格を埋める ▼▼▼
salesap as (
  SELECT
    *,
    FIRST_VALUE(CASE WHEN price = 100 THEN NULL ELSE price END IGNORE NULLS)
    OVER (
        PARTITION BY tsr_code, appoint_visit_syain, session_id 
        ORDER BY appoint_visit_plan_date ASC, ap_id ASC
        ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
    ) as filled_price
  FROM salesap_with_session
),

TSR as (
SELECT
  tsr_code,

  -- ▼ ここから新しいステータス分類の処理が始まります ▼
  CASE
    -- 1. 【最優先】ロンザンが3(現S)か4(元S)の場合
    WHEN company_status_ronzan = 3 THEN 'ロンザン現S'
    WHEN company_status_ronzan = 4 THEN 'ロンザン元S'

    -- 2. 【次に】レイノス(SK)が3(現S)か4(元S)の場合
    -- IN (3, 4) と書くことで「3または4」という条件を短く書けます
    WHEN company_status_sk IN (3, 4) THEN 'レイノス現元S'

    -- 3. 【次に】他部署のどれか一つにでも3か4がある場合
    WHEN
      company_status_rms IN (3, 4) OR
      company_status_siemple IN (3, 4) OR
      company_status_mode IN (3, 4) OR
      company_status_shinsotsu IN (3, 4) OR
      company_status_aroundtables IN (3, 4) OR
      company_status_jigyousyoukei IN (3, 4) OR
      company_status_shachomeikan IN (3, 4) OR
      company_status_mrace IN (3, 4) OR
      company_status_maBuying IN (3, 4) OR
      company_status_abilities IN (3, 4) OR
      company_status_grace IN (3, 4) OR
      company_status_raytech IN (3, 4) OR
      company_status_soshikiriron IN (3, 4) OR
      company_status_bt IN (3, 4) OR
      company_status_otoriyosetecho IN (3, 4) OR
      company_status_shigotozukan IN (3, 4) OR
      company_status_rayasset IN (3, 4) OR
      company_status_mediatimes IN (3, 4) OR
      company_status_raceforum IN (3, 4) OR
      company_status_hoic IN (3, 4) OR
      company_status_takumigiken IN (3, 4) OR
      company_status_jip IN (3, 4)
    THEN '他部署現元S'

    -- 4. 【次に】他部署のどれか一つにでも2がある場合
    WHEN
      company_status_rms = 2 OR
      company_status_siemple = 2 OR
      company_status_mode = 2 OR
      company_status_shinsotsu = 2 OR
      company_status_aroundtables = 2 OR
      company_status_jigyousyoukei = 2 OR
      company_status_shachomeikan = 2 OR
      company_status_mrace = 2 OR
      company_status_maBuying = 2 OR
      company_status_abilities = 2 OR
      company_status_grace = 2 OR
      company_status_raytech = 2 OR
      company_status_soshikiriron = 2 OR
      company_status_bt = 2 OR
      company_status_otoriyosetecho = 2 OR
      company_status_shigotozukan = 2 OR
      company_status_rayasset = 2 OR
      company_status_mediatimes = 2 OR
      company_status_raceforum = 2 OR
      company_status_hoic = 2 OR
      company_status_takumigiken = 2 OR
          company_status_jip = 2
    THEN '他部署管S'

    -- 5. 【その次に】ロンザンの残りのステータスを確認
    WHEN company_status_ronzan = 2 THEN 'ロンザン管S'
    WHEN company_status_ronzan = 1 THEN 'ロンザン準S'
    WHEN company_status_ronzan = 0 THEN 'ロンザン源泉'

    -- 6. 【最後】どれにも当てはまらない場合は、ロンザンの値を出力
    -- （※エラーを防ぐため、数値を文字列に変換しています）
    ELSE CAST(company_status_ronzan AS STRING)

  END AS contract_status -- 出力される新しいカラムの名前です（お好みで変更可能です）

FROM `r-group-bigdata.tsr.lms_company_info`)

SELECT
    ap_id,
    salesap.tsr_code,
    company_name,
    ap_kakutokusha,
    ap_homonsha,
    appoint_get_date,
    appoint_visit_plan_date,
    jisshibi,
    AP_source, -- 元々のAPソース
    true_ap_source AS True_AP_source, -- 今回のロジックで判定した真のAPソース
    shuho,
    visit_times,
    race_owner,
    appoint_visit_client_position,
    setsuritsu,
    TOKI_URIAGE,
    konki_rieki,
    CXL,
    result_status,
    prefecture,
    concat(zenzenki_uriage,"→",zenki_uriage,"→",konki_uriage,"億(",toshi,"/",tsuki,")") as uriage_suii,
    concat(zenzenki_rieki,"→",zenki_rieki,"→",konki_rieki,"億(",toshi,"/",tsuki,")") as rieki_suii,
    employee_num,
    industry1,
    TSR.contract_status as STATUS,
    case when COALESCE(filled_price, price) = 100 then "説明無し"
         when COALESCE(filled_price, price) = 200 then "58%+9%"
         when COALESCE(filled_price, price) = 300 then "62%+12%"
         when COALESCE(filled_price, price) = 400 then "65%+12%"
         when COALESCE(filled_price, price) = 500 then "67%+14%"
         when COALESCE(filled_price, price) = 600 then "固定報酬165万円＋69％＋16％"
         when COALESCE(filled_price, price) = 650 then "固定報酬120万円＋69％＋16％"
         when COALESCE(filled_price, price) = 700 then "固定報酬60万円＋69％＋16％"
         when COALESCE(filled_price, price) = 800 then "半常勤プラン"
         when COALESCE(filled_price, price) = 900 then "その他"
         else "-" end as price,
    appoint_visit_client_address,
    rn      
FROM salesap
LEFT JOIN TSR on salesap.tsr_code = TSR.tsr_code
WHERE appoint_get_date >= '2023-10-03'
and rn = 1
AND NOT (IFNULL(AP_source, '') = 'ロンザン現S' AND IFNULL(shuho, '') = 'PKM同席')
order by appoint_get_date
"""

sales_data = client.query(sales_data_query).result().to_dataframe()

sales_data['appoint_get_date'] = pd.to_datetime(sales_data['appoint_get_date'])
sales_data['appoint_visit_plan_date'] = pd.to_datetime(sales_data['appoint_visit_plan_date'])
sales_data['jisshibi'] = pd.to_datetime(sales_data['jisshibi'])

selected_sales_data = pd.merge(sales_data, calendar, on=("appoint_get_date"), how="left")

# %%
for kakutoku_df, homon_df in (
    (kakutoku_shokushu, homon_shokushu),
    (kakutoku_layer, homon_layer),
    (kakutoku_nenji, homon_nenji),
):
    selected_sales_data = pd.merge(selected_sales_data, kakutoku_df, on=("Q", "ap_kakutokusha"), how="left")
    selected_sales_data = pd.merge(selected_sales_data, homon_df, on=("Q", "ap_homonsha"), how="left")


# %%
selected_sales_data.columns

# %%
selected_sales_data = selected_sales_data[[
    'AP獲得職種', '訪問職種','AP獲得レイヤー', '訪問レイヤー', 'AP獲得年次', '訪問年次',
    'ap_id', 'tsr_code', 'company_name', 'ap_kakutokusha', 'ap_homonsha',
    'appoint_get_date', 'appoint_visit_plan_date', 'jisshibi','visit_times', 'rn', 
    'AP_source','True_AP_source', 'STATUS','shuho',  'race_owner', 'appoint_visit_client_position',
    'setsuritsu', 'TOKI_URIAGE', 'konki_rieki', 'uriage_suii', 'rieki_suii','employee_num', 'industry1', 'price','appoint_visit_client_address',
    'CXL', 'result_status', 'prefecture']]

# %%
to_str_columns(selected_sales_data, [
    "ap_id", "visit_times", "TOKI_URIAGE", "CXL", "result_status",
    "prefecture", "employee_num", "rn",
])
to_str_columns(selected_sales_data, ["appoint_get_date", "appoint_visit_plan_date", "jisshibi"], clean_value="NaT")
selected_sales_data["race_owner"] = selected_sales_data["race_owner"].astype(str).replace("<NA>", "")


# %%
selected_sales_data.replace([np.inf, -np.inf], np.nan, inplace=True)
selected_sales_data.fillna('', inplace=True)

sales_final = selected_sales_data.values.tolist()

# %%
#シートに記載する
SPREADSHEET_ID = '1Nfr_Zf8TvXhOXsWCKZaug0vdchC3WuYrC9VO-vWMOf8'
Sheet_NAME = 'salesAP!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,sales_final,service)

# %% [markdown]
# ## 本交渉データ

# %%
hon_data_query = """
WITH
  -- ------------------------------------------------------------------
  -- 事前準備: 定数、カレンダー、基本情報のCTE
  -- ------------------------------------------------------------------

  ConstsShuho AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 5500),
  ConstsAppointSource AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 110),
  ConstsApSourceKoho AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 19),
  ConstsYomi AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 9),
  ConstsYomi2 AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 9),
  ConstsSalesResults AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 32),
  
  CalendarInfo AS (
    SELECT yyyymmdd AS date, CONCAT(ki, "-", q, "Q") AS q
    FROM `r-group-bigdata.live_sugarcrm52.calendar_suka_master`
  ),

  LatestHonkoshoYomis AS (
    SELECT * EXCEPT(rn)
    FROM (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY anken_id ORDER BY yomi_torokubi DESC) AS rn
      FROM `r-group-bigdata.live_rhs.honkosho_yomis`
    )
    WHERE rn = 1
  ),

  -- ------------------------------------------------------------------
  -- 【真のAPソース用①】: 成約実績データの取得（社名クリーニング＆安全結合）
  -- ------------------------------------------------------------------
  honkosho_raw AS (
    SELECT
      kigyo.tsr_code,
      koho.sugarid AS candidate_no,
      concat(sya.sei, sya.mei) AS kigyo_tanto,
      REGEXP_REPLACE(kigyo.name, r'(株式会社|（株）|\(株\)|合同会社|（同）|\(同\)|有限会社|（有）|\(有\)|ホールディングス|HD|グループ|カンパニー|\s|　)', '') AS clean_name
    FROM `r-group-bigdata.live_rhs.honkoshos` hon
    LEFT JOIN `r-group-bigdata.live_rhs.ankens` an ON hon.anken_id = an.id
    LEFT JOIN `r-group-bigdata.live_rhs.kigyos` kigyo ON an.kigyo_id = kigyo.id
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` koho ON an.kohosha_id = koho.id
    LEFT JOIN `r-group-bigdata.live_company.syain` sya ON an.kigyo_tanto = sya.user_id
    WHERE kigyo.tsr_code IS NOT NULL
  ),
  honkosho_distinct AS (
    SELECT DISTINCT tsr_code, candidate_no, kigyo_tanto, clean_name
    FROM honkosho_raw
  ),
  contract_history_base AS (
    SELECT
      COALESCE(cli.tsr_code, dr_strict.tsr_code) AS tsr_code,
      CAST(ge.seiyaku_date AS DATE) AS yomi_torokubi
    FROM `r-group-bigdata.live_sugarcrm52.geppou_naitei_temp` ge
    LEFT JOIN `r-group-bigdata.live_spms.clients` cli ON ge.client_id = cli.id
    LEFT JOIN (
      SELECT id, REGEXP_REPLACE(client, r'(株式会社|（株）|\(株\)|合同会社|（同）|\(同\)|有限会社|（有）|\(有\)|ホールディングス|HD|グループ|カンパニー|\s|　)', '') AS clean_name 
      FROM `r-group-bigdata.live_sugarcrm52.geppou_naitei_temp`
    ) ge_clean ON ge.id = ge_clean.id
    LEFT JOIN honkosho_distinct dr_strict
      ON ge.candidate_no = dr_strict.candidate_no
      AND ge.client_tantou = dr_strict.kigyo_tanto
      AND (STRPOS(ge_clean.clean_name, dr_strict.clean_name) > 0 OR STRPOS(dr_strict.clean_name, ge_clean.clean_name) > 0)
    WHERE ge.scout_category LIKE "%ロンザン%" AND ge.seiyaku_date IS NOT NULL
  ),
  contract_history_arr AS (
    SELECT
      tsr_code,
      ARRAY_AGG(yomi_torokubi IGNORE NULLS ORDER BY yomi_torokubi DESC) AS contract_dates
    FROM contract_history_base
    WHERE tsr_code IS NOT NULL
    GROUP BY tsr_code
  ),

  -- ------------------------------------------------------------------
  -- 【真のAPソース用②】: sales_appoints の抽出と真のソース判定
  -- ------------------------------------------------------------------
  salesap_raw_base AS (
    SELECT 
      ap.id AS ap_id,
      ap.tsr_code,
      ap.company_name,
      ap.appoint_get_date,
      ap.appoint_visit_plan_date,
      ap.appoint_visit_syain,
      ap.appoint_visit_client_position,
      shuho.name AS shuho,
      CASE
        WHEN consts.name LIKE "%源泉%" THEN "源泉"
        WHEN consts.name LIKE "%RZ管S%" THEN "ロンザン管S"
        WHEN consts.name LIKE "%RZ現S%" THEN "ロンザン現S"
        WHEN consts.name LIKE "%RZ元S%" THEN "ロンザン元S"
        WHEN consts.name LIKE "%スカウト現S%" THEN "スカウト現元S"
        WHEN consts.name LIKE "%スカウト元S%" THEN "スカウト現元S"
        WHEN consts.name LIKE "%顧問現S%" THEN "他部署現元S"
        WHEN consts.name LIKE "%顧問元S%" THEN "他部署現元S"
        WHEN consts.name LIKE "%プロ時短現S%" THEN "他部署現元S"
        WHEN consts.name LIKE "%プロ時短元S%" THEN "他部署現元S"
        WHEN consts.name LIKE "%他部署現S%" THEN "他部署現元S"
        WHEN consts.name LIKE "%他部署元S%" THEN "他部署現元S"
        WHEN consts.name LIKE "%他部署管S%" THEN "他部署管S"
        WHEN consts.name LIKE "%顧問管S%" THEN "他部署管S"
        WHEN consts.name LIKE "%スカウト管S%" THEN "他部署管S"
        ELSE "その他"
      END AS apsource,
      ful.price_explanation3 AS price_code_raw,
      cal.q AS eigyo_q,
      -- CXLフラグの計算
      CASE 
        WHEN ap.deleted = 1 THEN "削除"
        WHEN ap.deleted = 2 THEN "CXL"
        WHEN ful.fulfills_date IS NULL AND ap.cxl_oikaden IS NOT NULL THEN "CXL"
        WHEN ful.fulfills_date IS NOT NULL THEN sales_results.name
        ELSE "未報告" 
      END AS CXL
    FROM `r-group-bigdata.live_rhs.sales_appoints` ap
    LEFT JOIN `r-group-bigdata.live_rhs.sales_appoint_fulfills` ful ON ap.id = ful.id
    LEFT JOIN ConstsShuho AS shuho ON SAFE_CAST(ap.shuho AS INT64) = shuho.code
    LEFT JOIN ConstsAppointSource AS consts ON SAFE_CAST(ap.appoint_source AS INT64) = consts.code
    LEFT JOIN ConstsSalesResults AS sales_results ON SAFE_CAST(ful.result_status AS INT64) = sales_results.code
    LEFT JOIN CalendarInfo AS cal ON ap.appoint_visit_plan_date = cal.date
    WHERE ap.tsr_code IS NOT NULL
  ),
  salesap_raw AS (
    SELECT * FROM salesap_raw_base WHERE CXL != '削除'
  ),
  salesap_history_prep AS (
    SELECT
      ap.*,
      (
        SELECT c_date FROM UNNEST(ch.contract_dates) AS c_date 
        WHERE c_date <= CAST(ap.appoint_get_date AS DATE) 
        ORDER BY c_date DESC LIMIT 1
      ) AS last_contract_date,
      LAG(ap.CXL) OVER (PARTITION BY ap.tsr_code ORDER BY ap.appoint_get_date ASC, ap.ap_id ASC) AS prev_cxl,
      LAG(ap.appoint_visit_plan_date) OVER (PARTITION BY ap.tsr_code ORDER BY ap.appoint_get_date ASC, ap.ap_id ASC) AS true_prev_visit_plan_date
    FROM salesap_raw ap
    LEFT JOIN contract_history_arr ch ON ap.tsr_code = ch.tsr_code
  ),
  salesap_state_calc AS (
    SELECT
      *,
      CASE 
        WHEN prev_cxl = '未報告' THEN 1 
        WHEN prev_cxl NOT IN ('CXL', '未報告') AND DATE_DIFF(CAST(appoint_get_date AS DATE), CAST(true_prev_visit_plan_date AS DATE), DAY) > 90 THEN 1 
        ELSE 0 
      END AS is_trigger_kans
    FROM salesap_history_prep
  ),
  salesap_true_source_prep AS (
    SELECT
      *,
      MAX(is_trigger_kans) OVER (PARTITION BY tsr_code ORDER BY appoint_get_date ASC, ap_id ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS is_kans_mode
    FROM salesap_state_calc
  ),
  salesap_with_true_source AS (
    SELECT
      *,
      CASE
        WHEN apsource IN ('スカウト現元S', '他部署現元S', '他部署管S') THEN apsource
        WHEN last_contract_date IS NOT NULL AND DATE_DIFF(CAST(appoint_get_date AS DATE), last_contract_date, DAY) <= 365 THEN 'ロンザン現S'
        WHEN last_contract_date IS NOT NULL AND DATE_DIFF(CAST(appoint_get_date AS DATE), last_contract_date, DAY) > 365 THEN 'ロンザン元S'
        WHEN is_kans_mode > 0 THEN 'ロンザン管S'
        WHEN prev_cxl IS NULL THEN '源泉'
        WHEN prev_cxl = 'CXL' THEN '源泉'
        WHEN prev_cxl NOT IN ('CXL', '未報告') AND DATE_DIFF(CAST(appoint_get_date AS DATE), CAST(true_prev_visit_plan_date AS DATE), DAY) <= 90 THEN '再訪'
        ELSE '源泉'
      END AS true_ap_source
    FROM salesap_true_source_prep
  ),

  -- ------------------------------------------------------------------
  -- 【真のAPソース用③】: 価格埋め用（本交渉クエリ側の FormattedSalesAppoints に相当）
  -- ------------------------------------------------------------------
  salesap_with_prev AS (
    SELECT
      *,
      LAG(appoint_visit_plan_date) OVER (PARTITION BY tsr_code, appoint_visit_syain ORDER BY appoint_visit_plan_date ASC, ap_id ASC) as prev_visit_plan_date
    FROM salesap_with_true_source
  ),
  salesap_with_session AS (
    SELECT
      *,
      SUM(CASE WHEN prev_visit_plan_date IS NULL THEN 0 WHEN DATE_DIFF(appoint_get_date, prev_visit_plan_date, DAY) > 90 THEN 1 ELSE 0 END) 
      OVER (PARTITION BY tsr_code, appoint_visit_syain ORDER BY appoint_visit_plan_date ASC, ap_id ASC) as session_id
    FROM salesap_with_prev
  ),
  FormattedSalesAppoints AS (
    SELECT
      *,
      FIRST_VALUE(CASE WHEN price_code_raw = 100 THEN NULL ELSE price_code_raw END IGNORE NULLS)
      OVER (PARTITION BY tsr_code, appoint_visit_syain, session_id ORDER BY appoint_visit_plan_date ASC, ap_id ASC ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) as filled_price_code
    FROM salesap_with_session
  ),

  -- ------------------------------------------------------------------
  -- LMS 企業ステータス情報
  -- ------------------------------------------------------------------
  LmsCompanyStatus AS (
    SELECT
      tsr_code,
      CASE company_status_sk
        WHEN 0 THEN "源泉" WHEN 1 THEN "営業前/実施未報告" WHEN 2 THEN "管S" WHEN 3 THEN "レイノス現S" WHEN 4 THEN "元S" ELSE "エラー" END AS SK,
      CASE company_status_ronzan
        WHEN 0 THEN "源泉" WHEN 1 THEN "営業前/実施未報告" WHEN 2 THEN "管S" WHEN 3 THEN "ロンザン現S" WHEN 4 THEN "ロンザン元S" ELSE "エラー" END AS RZ
    FROM `r-group-bigdata.tsr.lms_company_info`
  ),

  -- ------------------------------------------------------------------
  -- 主要データの結合と加工を行うCTE
  -- ------------------------------------------------------------------
  BaseHonkoshoData AS (
    SELECT
      hon.id AS honkosho_id,
      hon.anken_id AS anken_id,
      an.kohosha_id AS kohosha_id,
      kgy.tsr_code AS tsr_code,
      kgy.name AS kigyo_name,
      tsr.employee_num,
      case when tsr.race_owner is null then "" when tsr.race_owner = 0 then "オーナー" else "非オーナー" end as race_owner,
      ROUND(SAFE_DIVIDE(tsr.tokikessan_uriagedaka, 100000), 0) AS toki_uriage_hyakuman,
      ROUND(SAFE_DIVIDE(tsr.tokikessan_riekikin, 100000), 1) AS konki_rieki_hyakuman,
      hon.kosho_setteibi,
      FORMAT_DATE('%Y/%m/%d', hon.kosho_setteibi) AS hon_setteibi_formatted,
      FORMAT_DATE('%Y/%m/%d', hon.kosho_yoteibi) AS hon_yoteibi_formatted,
      FORMAT_DATE('%Y/%m/%d', hon.kosho_jisshibi) AS hon_jisshibi_formatted,
      hon.kosho_seq,
      cal.q AS settei_q,
      COALESCE(syi1.sei_plus, hon.kohosha_tanto) AS kohosha_tanto_name,
      syi2.sei_plus AS kigyo_tanto,
      
      -- アポイント/営業情報 (FormattedSalesAppoints から)
      fsa.ap_id,
      FORMAT_DATE('%Y/%m/%d', fsa.appoint_visit_plan_date) as appoint_visit_plan_date,
      fsa.eigyo_q,
      fsa.appoint_visit_client_position,
      fsa.shuho,
      fsa.apsource AS AP_source, -- 元々のソース
      fsa.true_ap_source AS True_AP_source, -- ★今回紐付けた真のAPソース
      
      COALESCE(fsa.filled_price_code, fsa.price_code_raw) AS final_price_code,
      
      consts_ap_koho.name AS kohosha_ap_source,
      shoki.tsr_code AS kohosha_shussin_kigyo_tsrcode,
      shoki.shusshin_kigyo AS kohosha_shusshin_kigyo_name,
      koho.annual_income,
      yomi.name AS yomi_name,
      COALESCE(yomi2.name, yomi.name) AS yomi_final,
      
      CASE
        WHEN lms_status.RZ = "ロンザン現S" THEN "ロンザン現S"
        WHEN lms_status.RZ = "ロンザン元S" THEN "ロンザン元S"
        WHEN lms_status.SK = "レイノス現S" THEN "レイノス現S"
        ELSE "それ以外"
      END AS current_status,
      
      CASE
        WHEN hon.kosho_setteibi = MIN(hon.kosho_setteibi) OVER (PARTITION BY kgy.tsr_code) THEN '初回'
        ELSE '2回目以降'
      END AS tsr_code_first_appearance,
      
      an.linked_shokikosho_id,
      
      -- ★重要: 本交渉設定日以前の、CXLされていない有効なアポを直近順に順位付け
      ROW_NUMBER() OVER (
          PARTITION BY hon.id 
          ORDER BY fsa.appoint_visit_plan_date DESC, fsa.ap_id DESC
      ) AS ap_rn,

      case when an.hanjokin = 20 then "半常勤" else "" end hanjokin

    FROM `r-group-bigdata.live_rhs.honkoshos` AS hon
    LEFT JOIN `r-group-bigdata.live_rhs.ankens` AS an ON hon.anken_id = an.id
    LEFT JOIN LatestHonkoshoYomis AS yomis ON an.id = yomis.anken_id
    LEFT JOIN `r-group-bigdata.live_rhs.kigyos` AS kgy ON an.kigyo_id = kgy.id
    LEFT JOIN `r-group-bigdata.tsr.company_info` AS tsr ON kgy.tsr_code = tsr.tsr_code
    LEFT JOIN `r-group-bigdata.live_rhs.shokikoshos` AS shoki ON an.linked_shokikosho_id = shoki.id
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` AS koho ON an.kohosha_id = koho.id
    LEFT JOIN `r-group-bigdata.live_rhs.ronzan_members` AS mem ON an.kigyo_tanto = mem.userid
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON hon.kohosha_tanto = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON an.kigyo_tanto = syi2.user_id
    LEFT JOIN LmsCompanyStatus AS lms_status ON kgy.tsr_code = lms_status.tsr_code
    LEFT JOIN ConstsApSourceKoho AS consts_ap_koho ON koho.ap_source = consts_ap_koho.code
    LEFT JOIN ConstsYomi AS yomi ON hon.yomi = yomi.code
    LEFT JOIN ConstsYomi2 AS yomi2 ON yomis.yomi = yomi2.code
    LEFT JOIN CalendarInfo AS cal ON hon.kosho_setteibi = cal.date

    -- ★変更: 本交渉の「直前の有効な営業」のみを紐付けるための結合条件
    LEFT JOIN FormattedSalesAppoints AS fsa 
      ON kgy.tsr_code = fsa.tsr_code 
      AND fsa.appoint_visit_plan_date <= hon.kosho_setteibi
      AND fsa.CXL != 'CXL' -- キャンセルされた営業は本交渉の起点にならないため除外（未報告は含む）
      AND fsa.true_ap_source != '再訪' -- ★追加: 再訪は起点ソースではないためスキップし、大元のアポに紐づける

    WHERE (hon.kosho_seq = 1 OR hon.kosho_seq_extra = 1)
      AND mem.id > 0
  )

-- ------------------------------------------------------------------
-- 最終結果の出力
-- ------------------------------------------------------------------
SELECT
  * EXCEPT(ap_rn, final_price_code)
  , CASE final_price_code
      WHEN 100 THEN "説明無し"
      WHEN 200 THEN "58%+9%"
      WHEN 300 THEN "62%+12%"
      WHEN 400 THEN "65%+12%"
      WHEN 500 THEN "67%+14%"
      WHEN 600 THEN "固定報酬165万円＋69％＋16％"
      WHEN 650 THEN "固定報酬120万円＋69％＋16％"
      WHEN 700 THEN "固定報酬60万円＋69％＋16％"
      WHEN 800 THEN "半常勤プラン"
      WHEN 900 THEN "その他"
      ELSE "-"
    END AS price_description
FROM BaseHonkoshoData
WHERE ap_rn = 1;
"""

hon_data = client.query(hon_data_query).result().to_dataframe()


hon_data['kosho_setteibi'] = pd.to_datetime(hon_data['kosho_setteibi'])
hon_data['appoint_visit_plan_date'] = pd.to_datetime(hon_data['appoint_visit_plan_date'])


selected_hon_data = hon_data[hon_data['kosho_setteibi'] >= '2022-10-01']


# %%
selected_hon_data.dtypes

# %%
calendar_kosho = calendar.rename(columns={"appoint_get_date": "kosho_setteibi"})
selected_hon_data = pd.merge(selected_hon_data, calendar_kosho, on=("kosho_setteibi"), how="left")


# %%
selected_hon_data = merge_kigyo_tanto_attrs(selected_hon_data)


# %%
selected_hon_data = selected_hon_data[[
       '企担：職種', '企担：レイヤー', '企担：年次','honkosho_id', 'anken_id', 'kohosha_id', 
       'tsr_code', 'kigyo_name','toki_uriage_hyakuman','konki_rieki_hyakuman','employee_num','AP_source','True_AP_source',
       'hon_setteibi_formatted','hon_yoteibi_formatted', 'hon_jisshibi_formatted',
       'kohosha_tanto_name', 'kigyo_tanto', 'kosho_seq','ap_id','appoint_visit_plan_date', 'shuho', 
       'kohosha_shussin_kigyo_tsrcode','annual_income','yomi_name', 'yomi_final', 'race_owner', 'appoint_visit_client_position',
       'price_description','tsr_code_first_appearance','hanjokin']]

# %%
selected_hon_data.columns

# %%
to_str_columns(selected_hon_data, [
    "honkosho_id", "anken_id", "kohosha_id", "toki_uriage_hyakuman",
    "konki_rieki_hyakuman", "employee_num", "kosho_seq", "ap_id", "annual_income",
])
to_str_columns(selected_hon_data, ["appoint_visit_plan_date"], clean_value="None")


# %%
selected_hon_data.dtypes

# %%
selected_hon_data.replace([np.inf, -np.inf], np.nan, inplace=True)
selected_hon_data.fillna('', inplace=True)

hon_final = selected_hon_data.values.tolist()

# %%
#シートに記載する
SPREADSHEET_ID = '1Nfr_Zf8TvXhOXsWCKZaug0vdchC3WuYrC9VO-vWMOf8'
Sheet_NAME = 'hon!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,hon_final,service)

# %% [markdown]
# ## 本交渉（人）

# %% [markdown]
# 

# %%
honnin_data_query = """
WITH
  -- 1. カレンダーマスタ (共通利用)
  calendar_master AS (
    SELECT
      yyyymmdd AS date,
      CONCAT(ki, "-", q, "Q") AS quarter
    FROM `r-group-bigdata.live_sugarcrm52.calendar_suka_master`
  ),

  -- 2. 定数マスタ (名称取得用)
  consts_shuho AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 5500),
  consts_source AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 110),
  consts_sales_results AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 32),

  -- ------------------------------------------------------------------
  -- 【真のAPソース用①】: 成約実績データの取得（社名クリーニング＆安全結合）
  -- ------------------------------------------------------------------
  honkosho_raw AS (
    SELECT
      kigyo.tsr_code,
      koho.sugarid AS candidate_no,
      concat(sya.sei, sya.mei) AS kigyo_tanto,
      REGEXP_REPLACE(kigyo.name, r'(株式会社|（株）|\(株\)|合同会社|（同）|\(同\)|有限会社|（有）|\(有\)|ホールディングス|HD|グループ|カンパニー|\s|　)', '') AS clean_name
    FROM `r-group-bigdata.live_rhs.honkoshos` hon
    LEFT JOIN `r-group-bigdata.live_rhs.ankens` an ON hon.anken_id = an.id
    LEFT JOIN `r-group-bigdata.live_rhs.kigyos` kigyo ON an.kigyo_id = kigyo.id
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` koho ON an.kohosha_id = koho.id
    LEFT JOIN `r-group-bigdata.live_company.syain` sya ON an.kigyo_tanto = sya.user_id
    WHERE kigyo.tsr_code IS NOT NULL
  ),
  honkosho_distinct AS (
    SELECT DISTINCT tsr_code, candidate_no, kigyo_tanto, clean_name
    FROM honkosho_raw
  ),
  contract_history_base AS (
    SELECT
      COALESCE(cli.tsr_code, dr_strict.tsr_code) AS tsr_code,
      CAST(ge.seiyaku_date AS DATE) AS yomi_torokubi
    FROM `r-group-bigdata.live_sugarcrm52.geppou_naitei_temp` ge
    LEFT JOIN `r-group-bigdata.live_spms.clients` cli ON ge.client_id = cli.id
    LEFT JOIN (
      SELECT id, REGEXP_REPLACE(client, r'(株式会社|（株）|\(株\)|合同会社|（同）|\(同\)|有限会社|（有）|\(有\)|ホールディングス|HD|グループ|カンパニー|\s|　)', '') AS clean_name 
      FROM `r-group-bigdata.live_sugarcrm52.geppou_naitei_temp`
    ) ge_clean ON ge.id = ge_clean.id
    LEFT JOIN honkosho_distinct dr_strict
      ON ge.candidate_no = dr_strict.candidate_no
      AND ge.client_tantou = dr_strict.kigyo_tanto
      AND (STRPOS(ge_clean.clean_name, dr_strict.clean_name) > 0 OR STRPOS(dr_strict.clean_name, ge_clean.clean_name) > 0)
    WHERE ge.scout_category LIKE "%ロンザン%" AND ge.seiyaku_date IS NOT NULL
  ),
  contract_history_arr AS (
    SELECT
      tsr_code,
      ARRAY_AGG(yomi_torokubi IGNORE NULLS ORDER BY yomi_torokubi DESC) AS contract_dates
    FROM contract_history_base
    WHERE tsr_code IS NOT NULL
    GROUP BY tsr_code
  ),

  -- ------------------------------------------------------------------
  -- 【真のAPソース用②】: sales_appoints の抽出と真のソース判定
  -- ------------------------------------------------------------------
  salesap_raw_base AS (
    SELECT 
      ap.id AS ap_id,
      ap.tsr_code,
      ap.company_name,
      ap.appoint_get_date,
      ap.appoint_visit_plan_date,
      ap.appoint_visit_syain,
      ap.appoint_visit_client_position,
      shuho.name AS shuho,
      consts.name AS original_ap_source, -- ★実際に入力された生のAPソース名を追加
      -- 元のクエリの区分分けを踏襲
      CASE
        WHEN consts.name LIKE "%源泉%" THEN "源泉"
        WHEN consts.name LIKE "%RZ管S%" THEN "ロンザン管S"
        WHEN consts.name LIKE "%RZ現S%" THEN "ロンザン現S"
        WHEN consts.name LIKE "%RZ元S%" THEN "ロンザン元S"
        WHEN consts.name LIKE "%スカウト現S%" OR consts.name LIKE "%スカウト元S%" THEN "スカウト現元S"
        WHEN consts.name LIKE "%顧問現S%" OR consts.name LIKE "%顧問元S%" OR consts.name LIKE "%プロ時短現S%" OR consts.name LIKE "%プロ時短元S%" OR consts.name LIKE "%他部署現S%" OR consts.name LIKE "%他部署元S%" THEN "他部署現元S"
        WHEN consts.name LIKE "%他部署管S%" OR consts.name LIKE "%顧問管S%" OR consts.name LIKE "%スカウト管S%" THEN "他部署管S"
        ELSE "その他"
      END AS apsource,
      ROUND(SAFE_DIVIDE(tsr.tokikessan_uriagedaka, 100000), 0) AS URIAGE,
      tsr.race_owner,
      -- CXLフラグの計算
      CASE 
        WHEN ap.deleted = 1 THEN "削除"
        WHEN ap.deleted = 2 THEN "CXL"
        WHEN ful.fulfills_date IS NULL AND ap.cxl_oikaden IS NOT NULL THEN "CXL"
        WHEN ful.fulfills_date IS NOT NULL THEN sales_results.name
        ELSE "未報告" 
      END AS CXL
    FROM `r-group-bigdata.live_rhs.sales_appoints` ap
    LEFT JOIN `r-group-bigdata.live_rhs.sales_appoint_fulfills` ful ON ap.id = ful.id
    LEFT JOIN `r-group-bigdata.tsr.company_info` tsr ON ap.tsr_code = tsr.tsr_code
    LEFT JOIN consts_shuho AS shuho ON SAFE_CAST(ap.shuho AS INT64) = shuho.code
    LEFT JOIN consts_source AS consts ON SAFE_CAST(ap.appoint_source AS INT64) = consts.code
    LEFT JOIN consts_sales_results AS sales_results ON SAFE_CAST(ful.result_status AS INT64) = sales_results.code
    WHERE ap.tsr_code IS NOT NULL
  ),
  salesap_raw AS (
    SELECT * FROM salesap_raw_base WHERE CXL != '削除'
  ),
  salesap_history_prep AS (
    SELECT
      ap.*,
      (
        SELECT c_date FROM UNNEST(ch.contract_dates) AS c_date 
        WHERE c_date <= CAST(ap.appoint_get_date AS DATE) 
        ORDER BY c_date DESC LIMIT 1
      ) AS last_contract_date,
      LAG(ap.CXL) OVER (PARTITION BY ap.tsr_code ORDER BY ap.appoint_get_date ASC, ap.ap_id ASC) AS prev_cxl,
      LAG(ap.appoint_visit_plan_date) OVER (PARTITION BY ap.tsr_code ORDER BY ap.appoint_get_date ASC, ap.ap_id ASC) AS true_prev_visit_plan_date
    FROM salesap_raw ap
    LEFT JOIN contract_history_arr ch ON ap.tsr_code = ch.tsr_code
  ),
  salesap_state_calc AS (
    SELECT
      *,
      CASE 
        WHEN prev_cxl = '未報告' THEN 1 
        WHEN prev_cxl NOT IN ('CXL', '未報告') AND DATE_DIFF(CAST(appoint_get_date AS DATE), CAST(true_prev_visit_plan_date AS DATE), DAY) > 90 THEN 1 
        ELSE 0 
      END AS is_trigger_kans
    FROM salesap_history_prep
  ),
  salesap_true_source_prep AS (
    SELECT
      *,
      MAX(is_trigger_kans) OVER (PARTITION BY tsr_code ORDER BY appoint_get_date ASC, ap_id ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS is_kans_mode
    FROM salesap_state_calc
  ),
  salesap_with_true_source AS (
    SELECT
      *,
      CASE
        WHEN apsource IN ('スカウト現元S', '他部署現元S', '他部署管S') THEN apsource
        WHEN last_contract_date IS NOT NULL AND DATE_DIFF(CAST(appoint_get_date AS DATE), last_contract_date, DAY) <= 365 THEN 'ロンザン現S'
        WHEN last_contract_date IS NOT NULL AND DATE_DIFF(CAST(appoint_get_date AS DATE), last_contract_date, DAY) > 365 THEN 'ロンザン元S'
        WHEN is_kans_mode > 0 THEN 'ロンザン管S'
        WHEN prev_cxl IS NULL THEN '源泉'
        WHEN prev_cxl = 'CXL' THEN '源泉'
        WHEN prev_cxl NOT IN ('CXL', '未報告') AND DATE_DIFF(CAST(appoint_get_date AS DATE), CAST(true_prev_visit_plan_date AS DATE), DAY) <= 90 THEN '再訪'
        ELSE '源泉'
      END AS true_ap_source
    FROM salesap_true_source_prep
  ),

  -- 4. Status データ (LMS企業情報のステータス)
  status_data AS (
    SELECT
      tsr_code,
      CASE
        WHEN company_status_sk = 0 THEN "源泉"
        WHEN company_status_sk = 1 THEN "営業前/実施未報告"
        WHEN company_status_sk = 2 THEN "管S"
        WHEN company_status_sk = 3 THEN "レイノス現S"
        WHEN company_status_sk = 4 THEN "元S"
        ELSE "エラー"
      END AS SK,
      CASE
        WHEN company_status_ronzan = 0 THEN "源泉"
        WHEN company_status_ronzan = 1 THEN "営業前/実施未報告"
        WHEN company_status_ronzan = 2 THEN "管S"
        WHEN company_status_ronzan = 3 THEN "ロンザン現S"
        WHEN company_status_ronzan = 4 THEN "ロンザン元S"
        ELSE "エラー"
      END AS RZ
    FROM `r-group-bigdata.tsr.lms_company_info`
  ),

  -- 5. 本交渉データと営業データの結合・直近アポの特定
  joined_base AS (
    SELECT
      s.ap_id,
      an.kohosha_id,
      hon.kosho_setteibi,
      sya.sei_plus AS kigyo_tanto,
      s.appoint_visit_plan_date,
      s.race_owner,
      s.appoint_visit_client_position,
      s.shuho,
      s.original_ap_source, -- ★ 実際に入力された生のAPソース名
      s.apsource AS AP_source, -- 元々のソース(大括り)
      s.true_ap_source AS True_AP_source, -- ★ 真のソース
      kgy.tsr_code,
      s.URIAGE,
      cal.quarter,
      -- STATUS判定
      CASE
        WHEN st.RZ = "ロンザン現S" THEN "ロンザン現S"
        WHEN st.RZ = "ロンザン元S" THEN "ロンザン元S"
        WHEN st.SK = "レイノス現S" THEN "レイノス現S"
        ELSE "それ以外"
      END AS STATUS,
      
      -- ★重要: 本交渉設定日以前の、CXLと再訪を除外した有効な起点アポを直近順に順位付け
      ROW_NUMBER() OVER (
        PARTITION BY hon.id 
        ORDER BY s.appoint_visit_plan_date DESC, s.ap_id DESC
      ) AS ap_rn
    FROM
      `r-group-bigdata.live_rhs.honkoshos` hon
    INNER JOIN `r-group-bigdata.live_rhs.ankens` an ON an.id = hon.anken_id
    INNER JOIN `r-group-bigdata.live_rhs.ronzan_members` mem ON an.kigyo_tanto = mem.userid
    LEFT JOIN `r-group-bigdata.live_rhs.kigyos` kgy ON an.kigyo_id = kgy.id
    LEFT JOIN `r-group-bigdata.live_company.syain` sya ON an.kigyo_tanto = sya.user_id
    LEFT JOIN calendar_master AS cal ON hon.kosho_setteibi = cal.date
    
    -- ★ 真のソースを付与した営業データとの結合（条件で絞り込み）
    LEFT JOIN salesap_with_true_source AS s 
      ON kgy.tsr_code = s.tsr_code 
      AND s.appoint_visit_plan_date <= hon.kosho_setteibi
      AND s.CXL != 'CXL' 
      AND s.true_ap_source != '再訪'

    LEFT JOIN status_data AS st ON kgy.tsr_code = st.tsr_code
    WHERE
      (hon.kosho_seq = 1 OR hon.kosho_seq_extra = 1)
      AND mem.id > 0
  ),

  -- 本交渉ごとに直近の起点アポ1件のみに絞る
  joined_result AS (
    SELECT
      *,
      1 AS jikeitetsu,
      appoint_visit_plan_date AS sort_date
    FROM joined_base
    WHERE ap_rn = 1
  )

-- 最終出力
SELECT
  ap_id,
  kohosha_id,
  kosho_setteibi,
  kigyo_tanto,
  appoint_visit_plan_date,
  race_owner,
  appoint_visit_client_position,
  shuho,
  original_ap_source, -- ★追加: 入力されたままのソース
  AP_source,          -- 既存: 大まかに分類されたソース
  True_AP_source,     -- 既存: 今回新たに判定した真のソース
  tsr_code,
  URIAGE,
  quarter,
  jikeitetsu,
  STATUS,
  1 AS row_num -- 常に1位のみ選択するため
FROM
  joined_result
-- ★ 元クエリの最終要件: 候補者・Qごとの最新アポイントのみ抽出
QUALIFY
  ROW_NUMBER() OVER (PARTITION BY kohosha_id, quarter ORDER BY sort_date DESC) = 1
"""

honnin_data = client.query(honnin_data_query).result().to_dataframe()

honnin_data['kosho_setteibi'] = pd.to_datetime(honnin_data['kosho_setteibi'])
honnin_data['appoint_visit_plan_date'] = pd.to_datetime(honnin_data['appoint_visit_plan_date'])


selected_honnin_data = honnin_data[honnin_data['kosho_setteibi'] >= '2022-10-01']

# %%
selected_honnin_data = pd.merge(selected_honnin_data, calendar_kosho, on=("kosho_setteibi"), how="left")
selected_honnin_data = merge_kigyo_tanto_attrs(selected_honnin_data)


# %%
selected_honnin_data.dtypes

# %%
selected_honnin_data = selected_honnin_data[[
       '企担：職種', '企担：レイヤー', '企担：年次',
       'ap_id', 'kohosha_id', 'kosho_setteibi', 'kigyo_tanto',
       'appoint_visit_plan_date', 'shuho', 'AP_source','True_AP_source','quarter',
       'tsr_code','URIAGE','appoint_visit_client_position','race_owner']]


# %%
to_str_columns(selected_honnin_data, ["ap_id", "kohosha_id", "URIAGE", "race_owner"])
to_str_columns(selected_honnin_data, ["kosho_setteibi", "appoint_visit_plan_date"], clean_value="None")


# %%
selected_honnin_data.replace([np.inf, -np.inf], np.nan, inplace=True)
selected_honnin_data.fillna('', inplace=True)

honnin_final = selected_honnin_data.values.tolist()

# %%
#シートに記載する
SPREADSHEET_ID = '1Nfr_Zf8TvXhOXsWCKZaug0vdchC3WuYrC9VO-vWMOf8'
Sheet_NAME = 'hon_nin!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,honnin_final,service)

# %% [markdown]
# ## 本交渉（社）

# %%
honsha_data_query = """
WITH
  -- 1. カレンダーマスタ
  calendar_master AS (
    SELECT
      yyyymmdd AS date,
      CONCAT(ki, "-", q, "Q") AS Q
    FROM
      `r-group-bigdata.live_sugarcrm52.calendar_suka_master`
  ),

  -- 2. システム定数
  sys_consts_shuho AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 5500),
  sys_consts_source AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 110),
  sys_consts_sales_results AS (SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 32),

  -- 3. TSRごとの初回交渉設定日（全期間を通じての初回判定用）
  FirstSetteibiByTsr AS (
    SELECT
      kgy.tsr_code,
      MIN(hon.kosho_setteibi) AS first_setteibi
    FROM `r-group-bigdata.live_rhs.honkoshos` AS hon
    INNER JOIN `r-group-bigdata.live_rhs.ankens` AS an ON hon.anken_id = an.id
    INNER JOIN `r-group-bigdata.live_rhs.kigyos` AS kgy ON an.kigyo_id = kgy.id
    WHERE (hon.kosho_seq = 1 OR hon.kosho_seq_extra = 1)
    GROUP BY kgy.tsr_code
  ),

  -- 4. 本交渉データの集計
  hon_sha_base AS (
    SELECT
      hon.id AS hon_id, -- IDを追加（一意に特定するため）
      kigyo.tsr_code,
      sya.sei_plus AS kigyo_tanto,
      MIN(hon.kosho_setteibi) AS kosho_setteibi,
      cal.Q AS hon_shaQ
    FROM `r-group-bigdata.live_rhs.honkoshos` AS hon
    INNER JOIN `r-group-bigdata.live_rhs.ankens` AS an ON an.id = hon.anken_id
    INNER JOIN `r-group-bigdata.live_rhs.kigyos` AS kigyo ON an.kigyo_id = kigyo.id
    INNER JOIN `r-group-bigdata.live_rhs.ronzan_members` AS mem ON an.kigyo_tanto = mem.userid
    LEFT JOIN `r-group-bigdata.live_company.syain` AS sya ON an.kigyo_tanto = sya.user_id
    LEFT JOIN calendar_master AS cal ON hon.kosho_setteibi = cal.date
    WHERE (hon.kosho_seq = 1 OR hon.kosho_seq_extra = 1)
    GROUP BY
      hon.id,
      sya.sei_plus,
      an.kigyo_id,
      kigyo.tsr_code,
      cal.Q
  ),

  -- ------------------------------------------------------------------
  -- 【真のAPソース用①】: 成約実績データの取得（社名クリーニング＆安全結合）
  -- ------------------------------------------------------------------
  honkosho_raw AS (
    SELECT
      kigyo.tsr_code,
      koho.sugarid AS candidate_no,
      concat(sya.sei, sya.mei) AS kigyo_tanto,
      REGEXP_REPLACE(kigyo.name, r'(株式会社|（株）|\(株\)|合同会社|（同）|\(同\)|有限会社|（有）|\(有\)|ホールディングス|HD|グループ|カンパニー|\s|　)', '') AS clean_name
    FROM `r-group-bigdata.live_rhs.honkoshos` hon
    LEFT JOIN `r-group-bigdata.live_rhs.ankens` an ON hon.anken_id = an.id
    LEFT JOIN `r-group-bigdata.live_rhs.kigyos` kigyo ON an.kigyo_id = kigyo.id
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` koho ON an.kohosha_id = koho.id
    LEFT JOIN `r-group-bigdata.live_company.syain` sya ON an.kigyo_tanto = sya.user_id
    WHERE kigyo.tsr_code IS NOT NULL
  ),
  honkosho_distinct AS (
    SELECT DISTINCT tsr_code, candidate_no, kigyo_tanto, clean_name
    FROM honkosho_raw
  ),
  contract_history_base AS (
    SELECT
      COALESCE(cli.tsr_code, dr_strict.tsr_code) AS tsr_code,
      CAST(ge.seiyaku_date AS DATE) AS yomi_torokubi
    FROM `r-group-bigdata.live_sugarcrm52.geppou_naitei_temp` ge
    LEFT JOIN `r-group-bigdata.live_spms.clients` cli ON ge.client_id = cli.id
    LEFT JOIN (
      SELECT id, REGEXP_REPLACE(client, r'(株式会社|（株）|\(株\)|合同会社|（同）|\(同\)|有限会社|（有）|\(有\)|ホールディングス|HD|グループ|カンパニー|\s|　)', '') AS clean_name 
      FROM `r-group-bigdata.live_sugarcrm52.geppou_naitei_temp`
    ) ge_clean ON ge.id = ge_clean.id
    LEFT JOIN honkosho_distinct dr_strict
      ON ge.candidate_no = dr_strict.candidate_no
      AND ge.client_tantou = dr_strict.kigyo_tanto
      AND (STRPOS(ge_clean.clean_name, dr_strict.clean_name) > 0 OR STRPOS(dr_strict.clean_name, ge_clean.clean_name) > 0)
    WHERE ge.scout_category LIKE "%ロンザン%" AND ge.seiyaku_date IS NOT NULL
  ),
  contract_history_arr AS (
    SELECT
      tsr_code,
      ARRAY_AGG(yomi_torokubi IGNORE NULLS ORDER BY yomi_torokubi DESC) AS contract_dates
    FROM contract_history_base
    WHERE tsr_code IS NOT NULL
    GROUP BY tsr_code
  ),

  -- ------------------------------------------------------------------
  -- 【真のAPソース用②】: sales_appoints の抽出と真のソース判定
  -- ------------------------------------------------------------------
  salesap_raw_base AS (
    SELECT 
      ap.id AS ap_id,
      ap.tsr_code,
      ap.company_name,
      ap.appoint_get_date,
      ap.appoint_visit_plan_date,
      ap.appoint_visit_syain,
      shuho.name AS shuho,
      CASE
        WHEN consts.name LIKE "%源泉%" THEN "源泉"
        WHEN consts.name LIKE "%RZ管S%" THEN "ロンザン管S"
        WHEN consts.name LIKE "%RZ現S%" THEN "ロンザン現S"
        WHEN consts.name LIKE "%RZ元S%" THEN "ロンザン元S"
        WHEN consts.name LIKE "%スカウト現S%" OR consts.name LIKE "%スカウト元S%" THEN "スカウト現元S"
        WHEN consts.name LIKE "%顧問現S%" OR consts.name LIKE "%顧問元S%" OR consts.name LIKE "%プロ時短現S%" OR consts.name LIKE "%プロ時短元S%" OR consts.name LIKE "%他部署現S%" OR consts.name LIKE "%他部署元S%" THEN "他部署現元S"
        WHEN consts.name LIKE "%他部署管S%" OR consts.name LIKE "%顧問管S%" OR consts.name LIKE "%スカウト管S%" THEN "他部署管S"
        ELSE "その他"
      END AS apsource,
      ROUND(SAFE_DIVIDE(tsr.tokikessan_uriagedaka, 100000), 0) AS URIAGE,
      ful.price_explanation3 AS price_raw,
      -- CXLフラグの計算
      CASE 
        WHEN ap.deleted = 1 THEN "削除"
        WHEN ap.deleted = 2 THEN "CXL"
        WHEN ful.fulfills_date IS NULL AND ap.cxl_oikaden IS NOT NULL THEN "CXL"
        WHEN ful.fulfills_date IS NOT NULL THEN sales_results.name
        ELSE "未報告" 
      END AS CXL
    FROM `r-group-bigdata.live_rhs.sales_appoints` ap
    LEFT JOIN `r-group-bigdata.live_rhs.sales_appoint_fulfills` ful ON ap.id = ful.id
    LEFT JOIN `r-group-bigdata.tsr.company_info` tsr ON ap.tsr_code = tsr.tsr_code
    LEFT JOIN sys_consts_shuho AS shuho ON SAFE_CAST(ap.shuho AS INT64) = shuho.code
    LEFT JOIN sys_consts_source AS consts ON SAFE_CAST(ap.appoint_source AS INT64) = consts.code
    LEFT JOIN sys_consts_sales_results AS sales_results ON SAFE_CAST(ful.result_status AS INT64) = sales_results.code
    WHERE ap.tsr_code IS NOT NULL
  ),
  salesap_raw AS (
    SELECT * FROM salesap_raw_base WHERE CXL != '削除'
  ),
  salesap_history_prep AS (
    SELECT
      ap.*,
      (
        SELECT c_date FROM UNNEST(ch.contract_dates) AS c_date 
        WHERE c_date <= CAST(ap.appoint_get_date AS DATE) 
        ORDER BY c_date DESC LIMIT 1
      ) AS last_contract_date,
      LAG(ap.CXL) OVER (PARTITION BY ap.tsr_code ORDER BY ap.appoint_get_date ASC, ap.ap_id ASC) AS prev_cxl,
      LAG(ap.appoint_visit_plan_date) OVER (PARTITION BY ap.tsr_code ORDER BY ap.appoint_get_date ASC, ap.ap_id ASC) AS true_prev_visit_plan_date
    FROM salesap_raw ap
    LEFT JOIN contract_history_arr ch ON ap.tsr_code = ch.tsr_code
  ),
  salesap_state_calc AS (
    SELECT
      *,
      CASE 
        WHEN prev_cxl = '未報告' THEN 1 
        WHEN prev_cxl NOT IN ('CXL', '未報告') AND DATE_DIFF(CAST(appoint_get_date AS DATE), CAST(true_prev_visit_plan_date AS DATE), DAY) > 90 THEN 1 
        ELSE 0 
      END AS is_trigger_kans
    FROM salesap_history_prep
  ),
  salesap_true_source_prep AS (
    SELECT
      *,
      MAX(is_trigger_kans) OVER (PARTITION BY tsr_code ORDER BY appoint_get_date ASC, ap_id ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS is_kans_mode
    FROM salesap_state_calc
  ),
  salesap_with_true_source AS (
    SELECT
      *,
      CASE
        WHEN apsource IN ('スカウト現元S', '他部署現元S', '他部署管S') THEN apsource
        WHEN last_contract_date IS NOT NULL AND DATE_DIFF(CAST(appoint_get_date AS DATE), last_contract_date, DAY) <= 365 THEN 'ロンザン現S'
        WHEN last_contract_date IS NOT NULL AND DATE_DIFF(CAST(appoint_get_date AS DATE), last_contract_date, DAY) > 365 THEN 'ロンザン元S'
        WHEN is_kans_mode > 0 THEN 'ロンザン管S'
        WHEN prev_cxl IS NULL THEN '源泉'
        WHEN prev_cxl = 'CXL' THEN '源泉'
        WHEN prev_cxl NOT IN ('CXL', '未報告') AND DATE_DIFF(CAST(appoint_get_date AS DATE), CAST(true_prev_visit_plan_date AS DATE), DAY) <= 90 THEN '再訪'
        ELSE '源泉'
      END AS true_ap_source
    FROM salesap_true_source_prep
  ),

  -- ------------------------------------------------------------------
  -- 【真のAPソース用③】: 価格補完ロジック
  -- ------------------------------------------------------------------
  salesap_with_prev AS (
    SELECT
      *,
      LAG(appoint_visit_plan_date) OVER (PARTITION BY tsr_code, appoint_visit_syain ORDER BY appoint_visit_plan_date ASC, ap_id ASC) as prev_visit_plan_date
    FROM salesap_with_true_source
  ),
  salesap_with_session AS (
    SELECT
      *,
      SUM(CASE WHEN prev_visit_plan_date IS NULL THEN 0 WHEN DATE_DIFF(appoint_get_date, prev_visit_plan_date, DAY) > 90 THEN 1 ELSE 0 END) 
      OVER (PARTITION BY tsr_code, appoint_visit_syain ORDER BY appoint_visit_plan_date ASC, ap_id ASC) as session_id
    FROM salesap_with_prev
  ),
  FormattedSalesAppoints AS (
    SELECT
      *,
      FIRST_VALUE(CASE WHEN price_raw = 100 THEN NULL ELSE price_raw END IGNORE NULLS)
      OVER (PARTITION BY tsr_code, appoint_visit_syain, session_id ORDER BY appoint_visit_plan_date ASC, ap_id ASC ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) as filled_price_code
    FROM salesap_with_session
  ),

  -- 6. 本交渉とSalesデータの結合・直近マッチング
  joined_ranked AS (
    SELECT
      hs.tsr_code,
      hs.kigyo_tanto,
      hs.kosho_setteibi,
      hs.hon_shaQ,
      s.ap_id,
      s.URIAGE,
      s.appoint_visit_plan_date,
      s.shuho,
      s.apsource AS AP_source,
      s.true_ap_source AS True_AP_source,
      
      -- Priceの整形 (未来補完した filled_price_code を優先)
      CASE COALESCE(s.filled_price_code, s.price_raw)
        WHEN 100 THEN "説明無し"
        WHEN 200 THEN "58%+9%"
        WHEN 300 THEN "62%+12%"
        WHEN 400 THEN "65%+12%"
        WHEN 500 THEN "67%+14%"
        WHEN 600 THEN "固定報酬165万円＋69％＋16％"
        WHEN 650 THEN "固定報酬120万円＋69％＋16％"
        WHEN 700 THEN "固定報酬60万円＋69％＋16％"
        WHEN 800 THEN "半常勤プラン"
        WHEN 900 THEN "その他"
        ELSE "-"
      END AS price,
      
      -- ロジックA: 本交渉ごとに、日付が「設定日以前」の中で「最も新しい」営業に順位1をつける
      ROW_NUMBER() OVER (
          PARTITION BY hs.hon_id 
          ORDER BY s.appoint_visit_plan_date DESC, s.ap_id DESC
      ) AS link_rank

    FROM
      hon_sha_base AS hs
    LEFT JOIN FormattedSalesAppoints AS s
      ON hs.tsr_code = s.tsr_code
      AND s.appoint_visit_plan_date <= hs.kosho_setteibi
      AND s.CXL != 'CXL' 
      AND s.true_ap_source != '再訪'
  ),

  -- 7. 重複排除用の順位付け (Q単位でのユニーク化)
  ranked_for_dedup AS (
    SELECT
      *,
      -- 同一TSR、同一Qの中で、本交渉設定日が早い順に番号を振る
      ROW_NUMBER() OVER (
          PARTITION BY tsr_code, hon_shaQ 
          ORDER BY kosho_setteibi ASC, ap_id DESC
      ) AS q_dedup_rn
    FROM joined_ranked
    WHERE link_rank = 1  -- まず「各本交渉」と「直近営業」のペアを1つに確定させる
  )

-- 最終出力
SELECT
  r.ap_id,
  r.tsr_code,
  r.URIAGE,
  r.kosho_setteibi,
  r.kigyo_tanto,
  r.appoint_visit_plan_date,
  r.shuho,
  r.AP_source,
  r.True_AP_source,
  r.hon_shaQ,
  1 AS jikeiretsu,
  r.price,
  -- 初回判定
  CASE
    WHEN r.kosho_setteibi = fst.first_setteibi THEN '初回'
    ELSE '2回目以降'
  END AS tsr_code_first_appearance
FROM
  ranked_for_dedup AS r
LEFT JOIN
  FirstSetteibiByTsr AS fst ON r.tsr_code = fst.tsr_code
WHERE
  -- ★ここでQ内の重複を確実に排除 (1番だけを残す)
  r.q_dedup_rn = 1;

"""

honsha_data = client.query(honsha_data_query).result().to_dataframe()

honsha_data['kosho_setteibi'] = pd.to_datetime(honsha_data['kosho_setteibi'])
honsha_data['appoint_visit_plan_date'] = pd.to_datetime(honsha_data['appoint_visit_plan_date'])

selected_honsha_data = honsha_data[honsha_data['kosho_setteibi'] >= '2022-10-01']




# %%
# selected_honsha_data.to_excel('selected_honsha_data.xlsx',sheet_name='new_sheet_name')

# %%
selected_honsha_data = pd.merge(selected_honsha_data, calendar_kosho, on=("kosho_setteibi"), how="left")
selected_honsha_data = merge_kigyo_tanto_attrs(selected_honsha_data)


# %%
selected_honsha_data.dtypes

# %%
selected_honsha_data = selected_honsha_data[[
       '企担：職種', '企担：レイヤー', '企担：年次','ap_id', 'tsr_code', 'URIAGE', 'kosho_setteibi', 'kigyo_tanto',
       'appoint_visit_plan_date', 'shuho', 'AP_source','True_AP_source', 'hon_shaQ',
       'price', 'tsr_code_first_appearance']]

# %%
to_str_columns(selected_honsha_data, ["ap_id", "URIAGE"])
to_str_columns(selected_honsha_data, ["kosho_setteibi", "appoint_visit_plan_date"], clean_value="None")


# %%
selected_honsha_data.replace([np.inf, -np.inf], np.nan, inplace=True)
selected_honsha_data.fillna('', inplace=True)

honsha_final = selected_honsha_data.values.tolist()

# %%
#シートに記載する
SPREADSHEET_ID = '1Nfr_Zf8TvXhOXsWCKZaug0vdchC3WuYrC9VO-vWMOf8'
Sheet_NAME = 'hon_sha!A'
Sheet_row = "2"
RANGE_NAME = Sheet_NAME+Sheet_row
ps.update_ss(SPREADSHEET_ID,RANGE_NAME,honsha_final,service)

# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%

