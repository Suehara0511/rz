# %%
import pandas as pd
import numpy as np

import ast
from google.oauth2 import service_account

import db_dtypes
from google.cloud import bigquery
from google.cloud import secretmanager

import python_ss.python_ss as ps

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

# BigQueryクライアントはここで1度だけ生成し、以降の全クエリで再利用する
client = bigquery.Client(credentials=credentials, project=credentials.project_id)

# %%
pd.set_option('display.max_rows', 100)
pd.set_option('display.max_columns', None)

# BigQuery/pandasの様々なNULL表現(NaN/None/NaT/<NA>)を文字列化後に一括で空文字へ統一するためのトークン
NA_STRING_TOKENS = ['nan', 'None', 'NaT', '<NA>']

def to_sheet_strings(df, columns):
    """指定列をスプレッドシート書き込み用の文字列に変換し、欠損値表現を空文字に統一する"""
    for col in columns:
        df[col] = df[col].astype(str).replace(NA_STRING_TOKENS, '')
    return df

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
doei_calendar = calendar[["日付","同営業日比較"]]

def q_calendar_for(date_col, as_str=False):
    """calendarシートからQ（四半期）マスタを、指定した日付列名に合わせて生成する"""
    q_cal = calendar[["日付","Q"]].rename(columns={"日付": date_col})
    q_cal[date_col] = pd.to_datetime(q_cal[date_col], errors='coerce')
    if as_str:
        q_cal[date_col] = q_cal[date_col].astype(str)
    return q_cal

# %%
#ロンザンメンバー情報
SPREADSHEET_ID = '1ULtRmgKopKne9EYf8SEkQlO9oPCviincWqFCtAgXFCA'
Sheet_NAME = '職種推移!A'
Sheet_row = ":F"
RANGE_NAME = Sheet_NAME+Sheet_row
rzmember = ps.get_ss(SPREADSHEET_ID,RANGE_NAME,service)
rzmember = rzmember[["Q","略氏名","レイヤー","職種"]]

def shokushu_layer_for(tanto_col, shokushu_label="候担職種", layer_label="候担レイヤー"):
    """rzmemberから、指定した担当者列名でマージ用の職種・レイヤーテーブルを都度生成する"""
    shokushu = rzmember.rename(columns={"略氏名": tanto_col, "職種": shokushu_label})[["Q", tanto_col, shokushu_label]]
    layer = rzmember.rename(columns={"略氏名": tanto_col, "レイヤー": layer_label})[["Q", tanto_col, layer_label]]
    return shokushu, layer

# %%
import time

def write_to_sheet(spreadsheet_id, sheet_range_prefix, data, start_row=2, chunk_size=5000):
    """データをchunk_size行ごとに分割してスプレッドシートへ書き込む（Sheets APIの行数上限・レート制限対策）"""
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        range_name = f"{sheet_range_prefix}{start_row + i}"
        ps.update_ss(spreadsheet_id, range_name, chunk, service)
        print(f"{start_row + i}行目から {len(chunk)}件のデータを書き込みました。")
        if i + chunk_size < len(data):
            time.sleep(1)  # APIの連続呼び出し制限（レートリミット）を回避
    print("全ての書き込みが完了しました！")

# %% [markdown]
# ## 初期交渉データ

# %%
shoki_data_query = """
WITH
-- CTE 1: APソースのマスタデータを準備
ap_source_master AS (
  SELECT
    code,
    name
  FROM `r-group-bigdata.live_rhs.sys_consts`
  WHERE group_code = 19),

-- CTE 2: 役職レイヤーのマスタデータを準備
layer_master AS (
  SELECT
    code,
    name
  FROM `r-group-bigdata.live_rhs.sys_consts`
  WHERE group_code = 25),

-- CTE 3: メインとなる交渉データに必要な情報を付与し、基本的な変換処理を行う
base_data AS (
  SELECT
    shoki.id,
    shoki.tenki_id,
    shoki.kohosha_id,
    CASE
      WHEN consts.name = '転機社長名鑑' THEN '転機'
      WHEN consts.name = '人事部経由' THEN '人事部紹介'
      WHEN consts.name IN ('顧問名鑑登録　解放者', '社外取締役名鑑　候補者') THEN '顧問名鑑登録者'
      WHEN consts.name IN ('HP反響', '上場企業役員DM', 'Gアポ') THEN 'その他'
      ELSE consts.name END AS APsource,
    layer.name AS layer,
    EXTRACT(YEAR FROM shoki.kosho_setteibi) - khs.birth_year AS age,
    shoki.annual_income,
    COALESCE(syi1.sei_plus, shoki.mendan_tanto) AS mendan_tanto,
    syi2.sei_plus AS ap_kakutokusha,
    shoki.kosho_setteibi,
    shoki.kosho_yoteibi,
    shoki.kosho_jisshibi,
    shoki.tsr_code,
    shoki.kosho_seq,
    shoki.saikosho_kaisu,
    shoki.saikosho_seq,
    shoki.valid_flag,
    shoki.deleted,
    -- ウィンドウ関数を使い、候補者ごとに前回交渉実施日からの経過日数を計算
    DATE_DIFF(
      shoki.kosho_setteibi,
      LAG(shoki.kosho_jisshibi) OVER (PARTITION BY shoki.kohosha_id ORDER BY shoki.kosho_setteibi),
      DAY) AS keikabi
  FROM `r-group-bigdata.live_rhs.shokikoshos` AS shoki
  LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` AS khs ON shoki.kohosha_id = khs.id
  LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON shoki.mendan_tanto = syi1.user_id
  LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON shoki.ap_kakutoku = syi2.user_id
  LEFT JOIN ap_source_master AS consts ON shoki.ap_source = consts.code
  LEFT JOIN layer_master AS layer ON shoki.max_bushoyakushoku = layer.code),

-- CTE 4: 1つ前のAPsourceの値を取得
data_with_prev_apsource AS (
  SELECT
    *,
    -- ウィンドウ関数を使い、1つ前のAPsourceを取得
    LAG(APsource) OVER (PARTITION BY kohosha_id ORDER BY kosho_setteibi) AS prev_APsource
  FROM base_data),

-- CTE 5: APsourceが変更されたかどうかのフラグを計算
data_with_aps_change AS (
  SELECT
    *,
    -- APsourceが前回から変更された場合に1を立てる
    CASE
      WHEN APsource != prev_APsource THEN 1
      ELSE 0 END AS APS_change
  FROM data_with_prev_apsource),

-- CTE 6: first_mendan_tantoを計算する前に、まずここで sai_flg を確定させる
calc_sai_flg AS (
  SELECT
    *,
    CASE
      WHEN kosho_seq = 1 THEN 1 -- 初回交渉
      WHEN APS_change = 1 THEN 1 -- APsourceが変更された場合
      WHEN keikabi > 90 THEN 2 -- 前回実施から90日以上経過
      ELSE 0
    END AS sai_flg
  FROM data_with_aps_change)

-- 最終的なSELECT文
SELECT
  id,
  tenki_id,
  kohosha_id,
  APsource,
  layer,
  age,
  annual_income,
  mendan_tanto,
  ap_kakutokusha,
  kosho_setteibi,
  kosho_yoteibi,
  kosho_jisshibi,
  kosho_seq,
  APS_change,
  keikabi,
  sai_flg,
  case when deleted = 0 then ""
       when deleted = 1 then "削除"
       when deleted = 2 then "CXL"
       else "-" end as CXL,
  -- 直近の `sai_flg = 1` になった時の `mendan_tanto` を取得して引き継ぐ
  LAST_VALUE(CASE WHEN sai_flg = 1 THEN mendan_tanto END IGNORE NULLS) OVER (
    PARTITION BY kohosha_id
    ORDER BY kosho_setteibi
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS first_mendan_tanto,

  tsr_code
FROM calc_sai_flg
where deleted != 1
ORDER BY kosho_setteibi ASC;
"""

shoki_data = client.query(shoki_data_query).result().to_dataframe()

shoki_data['kosho_setteibi'] = pd.to_datetime(shoki_data['kosho_setteibi'])
shoki_data['kosho_yoteibi'] = pd.to_datetime(shoki_data['kosho_yoteibi'])
shoki_data['kosho_jisshibi'] = pd.to_datetime(shoki_data['kosho_jisshibi'])

# %%
selected_shoki_data = shoki_data[shoki_data['kosho_setteibi'] >= '2021-06-30']

# %%
selected_shoki_data = pd.merge(selected_shoki_data, q_calendar_for("kosho_setteibi"), on="kosho_setteibi", how="left")

# %%
koho_shokushu, koho_layer = shokushu_layer_for("mendan_tanto")
selected_shoki_data = pd.merge(selected_shoki_data, koho_shokushu, on=("Q","mendan_tanto"), how="left")
selected_shoki_data = pd.merge(selected_shoki_data, koho_layer, on=("Q","mendan_tanto"), how="left")

# %%
# 必要な列を抽出後、明示的にコピーを作成して警告（SettingWithCopyWarning）を防ぐ
cols = [
    '候担職種', '候担レイヤー','id', 'tenki_id', 'kohosha_id', 'APsource', 'layer', 'age', 'annual_income',
    'mendan_tanto', 'ap_kakutokusha', 'kosho_setteibi', 'kosho_yoteibi',
    'kosho_jisshibi', 'kosho_seq', 'APS_change', 'keikabi', 'sai_flg','CXL','first_mendan_tanto','tsr_code'
]
selected_shoki_data = selected_shoki_data[cols].copy()

# %%
selected_shoki_data = to_sheet_strings(
    selected_shoki_data,
    ["id","tenki_id","kohosha_id","age","annual_income","kosho_setteibi","kosho_yoteibi",
     "kosho_jisshibi","kosho_seq","APS_change","keikabi","sai_flg","CXL"]
)

# %%
selected_shoki_data.replace([np.inf, -np.inf], np.nan, inplace=True)
selected_shoki_data.fillna('', inplace=True)

shoki_final = selected_shoki_data.values.tolist()

# %%
# シート情報
SPREADSHEET_ID = '1cy7WA-vAW_51PEpjmPNlo79ZvHB0GSPS0c2D_y9BYDg'
write_to_sheet(SPREADSHEET_ID, 'shoki!A', shoki_final)

# %% [markdown]
# ## 本交渉データ

# %%
selected_hon_data_query = """
WITH
-- =================================================================
-- マスタデータ準備セクション
-- 必要なマスタデータを事前にCTEとして定義し、再利用しやすくする
-- =================================================================

-- CTE 1: APソースのマスタデータ (group_code = 19)
ap_source_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 19
),

-- CTE 2: 役職レイヤーのマスタデータ (group_code = 25)
layer_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 25
),

-- CTE 3: ヨミのマスタデータ (group_code = 9)
yomi_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 9
),

-- CTE 4: 役職クラスのマスタデータ (group_code = 10)
yakushoku_class_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 10
),

-- =================================================================
-- 初期交渉データ準備セクション (元の`SHOKIS` CTEに相当)
-- =================================================================

-- CTE 5: 候補者ごとの初回接触日を計算
shokikoshos_with_initial_date AS (
  SELECT
    *,
    FIRST_VALUE(kosho_jisshibi IGNORE NULLS) OVER (PARTITION BY kohosha_id ORDER BY kosho_jisshibi) AS initial_contact_date
  FROM
    `r-group-bigdata.live_rhs.shokikoshos`
),

-- CTE 6: 初期交渉データの中間処理 (フラグ計算の前段階)
shoki_base AS (
  SELECT
    shk.id,
    shk.tenki_id,
    shk.kohosha_id,
    shk.ap_source,
    layer.name AS layer,
    shk.annual_income,
    COALESCE(syi1.sei_plus, shk.mendan_tanto) AS mendan_tanto,
    syi2.sei_plus AS ap_kakutokusha,
    shk.kosho_setteibi,
    shk.kosho_yoteibi,
    shk.kosho_jisshibi,
    shk.kosho_seq,
    shk.saikosho_kaisu,
    shk.saikosho_seq,
    shk.valid_flag,
    shk.initial_contact_date,
    -- 前回交渉実施日からの経過日数を計算
    DATE_DIFF(shk.kosho_setteibi, LAG(shk.kosho_jisshibi) OVER (PARTITION BY shk.kohosha_id ORDER BY shk.kosho_jisshibi), DAY) AS keikabi
  FROM
    shokikoshos_with_initial_date AS shk
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON shk.mendan_tanto = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON shk.ap_kakutoku = syi2.user_id
    LEFT JOIN layer_master AS layer ON shk.max_bushoyakushoku = layer.code
),

-- CTE 7: 初期交渉データの sai_flg を計算
shoki_calc_sai_flg AS (
  SELECT
    *,
    -- sai_flgを計算
    CASE
      WHEN kosho_seq = 1 THEN 1 -- 初回交渉
      -- APソースが前回から変更された場合
      WHEN ap_source != LAG(ap_source) OVER (PARTITION BY kohosha_id ORDER BY kosho_setteibi) THEN 1
      WHEN keikabi > 90 THEN 2 -- 前回実施から90日以上経過
      ELSE 0
    END AS sai_flg
  FROM
    shoki_base
),

-- CTE 7.5: 初期交渉データ内で first_mendan_tanto を引き継ぎ計算する
shoki_final AS (
  SELECT
    *,
    -- 直近の `sai_flg = 1` になった時の `mendan_tanto` を取得して引き継ぐ
    LAST_VALUE(CASE WHEN sai_flg = 1 THEN mendan_tanto END IGNORE NULLS) OVER (
      PARTITION BY kohosha_id
      ORDER BY kosho_setteibi
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS first_mendan_tanto
  FROM
    shoki_calc_sai_flg
),

-- =================================================================
-- 本交渉データ準備セクション (元の`HONS` CTEに相当)
-- =================================================================

-- CTE 8: 案件ごとの最新のヨミを取得
latest_yomis AS (
  SELECT
    anken_id,
    yomi
  FROM (
    SELECT
      anken_id,
      yomi,
      ROW_NUMBER() OVER (PARTITION BY anken_id ORDER BY yomi_torokubi DESC) AS rn
    FROM
      `r-group-bigdata.live_rhs.honkosho_yomis`
  )
  WHERE
    rn = 1
),

-- CTE 10: 本交渉データと関連データを結合
hons_base AS (
  SELECT
    hon.id AS honkosho_id,
    hon.anken_id,
    an.kohosha_id,
    an.linked_shokikosho_id,
    kgy.tsr_code,
    kgy.name AS kigyo_name,
    -- APソースを初期交渉と候補者マスタから取得し、優先度付け
    COALESCE(consts1.name, consts2.name) AS AP_source_raw,
    shoki.annual_income,
    shoki.layer,
    shoki.initial_contact_date,
    shoki.kosho_setteibi AS shoki_setteibi,
    shoki.kosho_jisshibi AS shoki_jisshibi,
    hon.kosho_setteibi AS hon_setteibi,
    hon.kosho_yoteibi AS hon_yoteibi,
    hon.kosho_jisshibi AS hon_jisshibi,
    COALESCE(syi1.sei_plus, hon.kohosha_tanto) AS kohosha_tanto,
    syi2.sei_plus AS kigyo_tanto,
    hon.kosho_seq AS hon_seq,
    shoki.kosho_seq AS shoki_seq,
    shoki.sai_flg,
    DATE_DIFF(hon.kosho_setteibi, shoki.kosho_jisshibi, DAY) AS jisshibi_sa,
    yomi1.name AS yomi,
    -- 最終的なヨミを決定
    COALESCE(yomi2.name, yomi1.name) AS yomi_final,
    ROUND(tsr.tokikessan_uriagedaka / 100000, 0) AS uriage,
    consts3.name AS yakushoku_class,
    -- shoki_final で計算した first_mendan_tanto を取得
    shoki.first_mendan_tanto,
        case when an.hanjokin = 20 then "半常勤"
         else "" end as hanjokin
  FROM
    `r-group-bigdata.live_rhs.honkoshos` AS hon
    LEFT JOIN `r-group-bigdata.live_rhs.ankens` AS an ON hon.anken_id = an.id
    LEFT JOIN shoki_final AS shoki ON an.linked_shokikosho_id = shoki.id
    LEFT JOIN `r-group-bigdata.live_rhs.kigyos` AS kgy ON an.kigyo_id = kgy.id
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` AS koho ON an.kohosha_id = koho.id
    LEFT JOIN `r-group-bigdata.tsr.company_info` AS tsr ON kgy.tsr_code = tsr.tsr_code
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON hon.kohosha_tanto = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON an.kigyo_tanto = syi2.user_id
    LEFT JOIN latest_yomis AS ly ON an.id = ly.anken_id
    -- マスタ結合
    LEFT JOIN ap_source_master AS consts1 ON shoki.ap_source = consts1.code
    LEFT JOIN ap_source_master AS consts2 ON koho.ap_source = consts2.code
    LEFT JOIN yomi_master AS yomi1 ON hon.yomi = yomi1.code
    LEFT JOIN yomi_master AS yomi2 ON ly.yomi = yomi2.code
    LEFT JOIN yakushoku_class_master AS consts3 ON hon.yakushoku_class = consts3.code
  WHERE hon.kosho_seq = 1
)

-- =================================================================
-- 最終的な出力
-- =================================================================
SELECT
  honkosho_id,
  anken_id,
  kohosha_id,
  linked_shokikosho_id,
  tsr_code,
  kigyo_name,
  annual_income,
  layer,
  initial_contact_date,
  -- 日付のフォーマット
  FORMAT_DATE('%Y-%m-%d', shoki_setteibi) AS shoki_setteibi,
  FORMAT_DATE('%Y-%m-%d', shoki_jisshibi) AS shoki_jisshibi,
  FORMAT_DATE('%Y-%m-%d', hon_setteibi) AS hon_setteibi,
  FORMAT_DATE('%Y-%m-%d', hon_yoteibi) AS hon_yoteibi,
  FORMAT_DATE('%Y-%m-%d', hon_jisshibi) AS hon_jisshibi,
  kohosha_tanto,
  kigyo_tanto,
  hon_seq,
  shoki_seq,
  jisshibi_sa,
  yomi,
  yomi_final,
  uriage,
  yakushoku_class,
  first_mendan_tanto,
  hanjokin,
  -- APsourceを分かりやすいカテゴリに分類
  CASE
    WHEN AP_source_raw = '転機社長名鑑' THEN '転機'
    WHEN AP_source_raw = '人事部経由' THEN '人事部紹介'
    WHEN AP_source_raw IN ('顧問名鑑登録　解放者', '社外取締役名鑑　候補者') THEN '顧問名鑑登録者'
    WHEN AP_source_raw IN ('HP反響', '上場企業役員DM', 'Gアポ') THEN 'その他'
    ELSE AP_source_raw
  END AS APsource,
  -- 最終的なフラグ `sai_flg2` を計算
  CASE
    WHEN shoki_jisshibi IS NULL THEN 2
    WHEN jisshibi_sa > 90 THEN 2
    ELSE sai_flg
  END AS sai_flg2
FROM hons_base
ORDER BY
  anken_id;
"""

hon_data = client.query(selected_hon_data_query).result().to_dataframe()

# %%
selected_hon_data = hon_data[hon_data['hon_setteibi'] >= '2022-10-01']
selected_hon_data = selected_hon_data[selected_hon_data['hon_seq'] == 1]

# %%
selected_hon_data = pd.merge(selected_hon_data, q_calendar_for("hon_setteibi", as_str=True), on="hon_setteibi", how="left")

# %%
koho_shokushu, koho_layer = shokushu_layer_for("kohosha_tanto")
selected_hon_data = pd.merge(selected_hon_data, koho_shokushu, on=("Q","kohosha_tanto"), how="left")
selected_hon_data = pd.merge(selected_hon_data, koho_layer, on=("Q","kohosha_tanto"), how="left")

kigyo_shokushu, _ = shokushu_layer_for("kigyo_tanto", shokushu_label="企担職種")
selected_hon_data = pd.merge(selected_hon_data, kigyo_shokushu, on=("Q","kigyo_tanto"), how="left")

# %%
selected_hon_data = selected_hon_data[["候担職種","企担職種","候担レイヤー","honkosho_id","anken_id","kohosha_id","linked_shokikosho_id","tsr_code","kigyo_name","APsource","initial_contact_date",
                             "shoki_jisshibi","hon_setteibi","hon_jisshibi","kohosha_tanto","kigyo_tanto",
                             "jisshibi_sa","hon_seq","sai_flg2","yomi","yomi_final","annual_income","layer","uriage","yakushoku_class",'first_mendan_tanto','hanjokin']]

# %%
selected_hon_data = to_sheet_strings(
    selected_hon_data,
    ["honkosho_id","anken_id","kohosha_id","linked_shokikosho_id","initial_contact_date",
     "shoki_jisshibi","hon_jisshibi","jisshibi_sa","hon_seq","sai_flg2","yomi","yomi_final",
     "annual_income","layer","uriage","hanjokin"]
)

# %%
selected_hon_data.replace([np.inf, -np.inf], np.nan, inplace=True)
selected_hon_data.fillna('', inplace=True)

hon_final = selected_hon_data.values.tolist()

# %%
SPREADSHEET_ID = '1cy7WA-vAW_51PEpjmPNlo79ZvHB0GSPS0c2D_y9BYDg'
write_to_sheet(SPREADSHEET_ID, 'hon!A', hon_final)

# %% [markdown]
# ## 本交渉（人）

# %%
honnin_data_query = """
WITH
-- =================================================================
-- マスタデータ準備セクション
-- 必要なマスタデータを事前にCTEとして定義し、再利用しやすくする
-- =================================================================

-- CTE 1: APソースのマスタデータ (group_code = 19)
ap_source_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 19
),

-- CTE 2: 役職レイヤーのマスタデータ (group_code = 25)
layer_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 25
),

-- CTE 3: 四半期カレンダーのマスタデータ
calendar_master AS (
  SELECT
    yyyymmdd,
    CONCAT(ki,"-",q,"Q") AS Q
  FROM `r-group-bigdata.live_sugarcrm52.calendar_suka_master`
),

-- =================================================================
-- 初期交渉データ準備セクション (元の`SHOKIS` CTEに相当)
-- =================================================================

-- CTE 4: 候補者ごとの初回接触日を計算
shokikoshos_with_initial_date AS (
  SELECT
    *,
    FIRST_VALUE(kosho_jisshibi IGNORE NULLS) OVER (PARTITION BY kohosha_id ORDER BY kosho_jisshibi) AS initial_contact_date
  FROM
    `r-group-bigdata.live_rhs.shokikoshos`
),

-- CTE 5: 初期交渉データの中間処理 (フラグ計算の前段階)
shoki_base AS (
  SELECT
    shk.id,
    shk.tenki_id,
    shk.kohosha_id,
    shk.ap_source,
    layer.name AS layer,
    shk.annual_income,
    COALESCE(syi1.sei_plus, shk.mendan_tanto) AS mendan_tanto,
    syi2.sei_plus AS ap_kakutokusha,
    shk.kosho_setteibi,
    shk.kosho_yoteibi,
    shk.kosho_jisshibi,
    shk.kosho_seq,
    shk.saikosho_kaisu,
    shk.saikosho_seq,
    shk.valid_flag,
    shk.initial_contact_date,
    -- 前回交渉実施日からの経過日数を計算
    DATE_DIFF(shk.kosho_setteibi, LAG(shk.kosho_jisshibi) OVER (PARTITION BY shk.kohosha_id ORDER BY shk.kosho_jisshibi), DAY) AS keikabi
  FROM
    shokikoshos_with_initial_date AS shk
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON shk.mendan_tanto = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON shk.ap_kakutoku = syi2.user_id
    LEFT JOIN layer_master AS layer ON shk.max_bushoyakushoku = layer.code
),

-- CTE 6: 初期交渉データの最終準備 (sai_flgを計算)
shoki_final AS (
  SELECT
    *,
    -- sai_flgを計算
    CASE
      WHEN kosho_seq = 1 THEN 1 -- 初回交渉
      -- APソースが前回から変更された場合
      WHEN ap_source != LAG(ap_source) OVER (PARTITION BY kohosha_id ORDER BY kosho_setteibi) THEN 1
      WHEN keikabi > 90 THEN 2 -- 前回実施から90日以上経過
      ELSE 0
    END AS sai_flg
  FROM
    shoki_base
),

-- =================================================================
-- 本交渉データ準備セクション (元の`HON_NINS`関連のCTEに相当)
-- =================================================================

-- CTE 7: 本交渉データと関連データを結合
hon_nins_base AS (
  SELECT
    hon.id AS honkosho_id,
    hon.anken_id AS anken_id,
    an.kohosha_id AS kohosha_id,
    an.linked_shokikosho_id,
    kgy.tsr_code AS tsr_code,
    kgy.name AS company_name,
    -- APソースを初期交渉と候補者マスタから取得し、優先度付け
    COALESCE(consts1.name, consts2.name) AS ap_source_raw,
    shoki.annual_income,
    shoki.layer,
    shoki.initial_contact_date,
    shoki.kosho_setteibi AS shoki_setteibi,
    shoki.kosho_jisshibi AS shoki_jisshibi,
    hon.kosho_setteibi AS hon_setteibi,
    hon.kosho_yoteibi AS hon_yoteibi,
    hon.kosho_jisshibi AS hon_jisshibi,
    COALESCE(syi1.sei_plus, hon.kohosha_tanto) AS kohosha_tanto,
    syi2.sei_plus AS kigyo_tanto,
    cal.Q,
    shoki.kosho_seq,
    shoki.sai_flg,
    -- 交渉ステータスを判定
    CASE
      WHEN hon.kosho_yoteibi >= CURRENT_DATE("Asia/Tokyo") THEN '実施前'
      WHEN hon.jisshi_flag = 2 AND hon.deleted = 2 THEN "CXL"
      WHEN hon.jisshi_flag = 0 AND hon.deleted = 0 AND hon.nittei_chosei = 1 THEN "日程調整中"
      WHEN hon.jisshi_flag = 1 THEN '実施'
      WHEN hon.jisshi_flag = 0 THEN '未報告'
      ELSE CAST(hon.jisshi_flag AS STRING)
    END AS status
  FROM
    `r-group-bigdata.live_rhs.honkoshos` AS hon
    LEFT JOIN `r-group-bigdata.live_rhs.ankens` AS an ON hon.anken_id = an.id
    LEFT JOIN shoki_final AS shoki ON an.linked_shokikosho_id = shoki.id
    LEFT JOIN `r-group-bigdata.live_rhs.kigyos` AS kgy ON an.kigyo_id = kgy.id
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` AS koho ON an.kohosha_id = koho.id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON hon.kohosha_tanto = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON an.kigyo_tanto = syi2.user_id
    LEFT JOIN calendar_master AS cal ON hon.kosho_setteibi = cal.yyyymmdd
    LEFT JOIN ap_source_master AS consts1 ON shoki.ap_source = consts1.code
    LEFT JOIN ap_source_master AS consts2 ON koho.ap_source = consts2.code
  WHERE
    hon.kosho_seq = 1
),

-- CTE 8: 最終的なデータ加工とランキング付け
hon_nins_ranked AS (
  SELECT
    *,
    -- APsourceを分かりやすいカテゴリに分類
    CASE
      WHEN ap_source_raw = '転機社長名鑑' THEN '転機'
      WHEN ap_source_raw = '人事部経由' THEN '人事部紹介'
      WHEN ap_source_raw IN ('顧問名鑑登録　解放者', '社外取締役名鑑　候補者') THEN '顧問名鑑登録者'
      WHEN ap_source_raw IN ('HP反響', '上場企業役員DM', 'Gアポ') THEN 'その他'
      ELSE ap_source_raw
    END AS ap_source,
    -- 初期交渉実施日と本交渉設定日の差を計算
    DATE_DIFF(hon_setteibi, shoki_jisshibi, DAY) AS jisshibi_sa,
    -- 候補者ごと、四半期ごとの交渉順位を計算
    ROW_NUMBER() OVER (PARTITION BY kohosha_id, Q ORDER BY hon_setteibi ASC) AS rn
  FROM hon_nins_base
)

-- =================================================================
-- 最終的な出力
-- =================================================================
SELECT
  honkosho_id,
  anken_id,
  kohosha_id,
  linked_shokikosho_id,
  tsr_code,
  company_name,
  ap_source,
  annual_income,
  layer,
  initial_contact_date,
  FORMAT_DATE('%Y/%m/%d', shoki_setteibi) AS shoki_setteibi,
  FORMAT_DATE('%Y/%m/%d', shoki_jisshibi) AS shoki_jisshibi,
  FORMAT_DATE('%Y/%m/%d', hon_setteibi) AS hon_setteibi,
  FORMAT_DATE('%Y/%m/%d', hon_yoteibi) AS hon_yoteibi,
  FORMAT_DATE('%Y/%m/%d', hon_jisshibi) AS hon_jisshibi,
  kohosha_tanto,
  kigyo_tanto,
  Q,
  kosho_seq,
  status,
  jisshibi_sa,
  -- 最終的なフラグ `sai_flg2` を計算
  CASE
    WHEN shoki_jisshibi IS NULL THEN 2
    WHEN jisshibi_sa > 90 THEN 2
    ELSE sai_flg
  END AS sai_flg2
FROM hon_nins_ranked
WHERE
  rn = 1 -- 候補者ごと、四半期ごとの最初の交渉のみを抽出
ORDER BY
  hon_setteibi;
"""

honnin_data = client.query(honnin_data_query).result().to_dataframe()

# %%
selected_honnin_data = honnin_data[honnin_data['hon_setteibi'] >= '2022-10-01']

# %%
koho_shokushu, koho_layer = shokushu_layer_for("kohosha_tanto")
selected_honnin_data = pd.merge(selected_honnin_data, koho_shokushu, on=("Q","kohosha_tanto"), how="left")
selected_honnin_data = pd.merge(selected_honnin_data, koho_layer, on=("Q","kohosha_tanto"), how="left")

# %%
selected_honnin_data = selected_honnin_data[['候担職種', '候担レイヤー','kohosha_id',
       'initial_contact_date', 'shoki_jisshibi', 'hon_setteibi',
       'kohosha_tanto', 'ap_source', 'Q', 'jisshibi_sa', 'sai_flg2', 'annual_income', 'layer']]

# %%
selected_honnin_data = to_sheet_strings(
    selected_honnin_data,
    ["kohosha_id","initial_contact_date","jisshibi_sa","sai_flg2","annual_income"]
)

# %%
selected_honnin_data.replace([np.inf, -np.inf], np.nan, inplace=True)
selected_honnin_data.fillna('', inplace=True)

honnin_final = selected_honnin_data.values.tolist()

# %%
SPREADSHEET_ID = '1cy7WA-vAW_51PEpjmPNlo79ZvHB0GSPS0c2D_y9BYDg'
write_to_sheet(SPREADSHEET_ID, 'hon_nin!A', honnin_final)

# %% [markdown]
# ## 本交渉（社）

# %%
honsha_data_query = """
WITH
-- =================================================================
-- マスタデータ準備セクション
-- 必要なマスタデータを事前にCTEとして定義し、再利用しやすくする
-- =================================================================

-- CTE 1: APソースのマスタデータ (group_code = 19)
ap_source_master AS (
  SELECT code, name FROM `r-group-bigdata.live_rhs.sys_consts` WHERE group_code = 19
),

-- CTE 2: 四半期カレンダーのマスタデータ
calendar_master AS (
  SELECT
    yyyymmdd,
    CONCAT(ki,"-",q,"Q") AS Q
  FROM `r-group-bigdata.live_sugarcrm52.calendar_suka_master`
),

-- =================================================================
-- データ結合と基本加工セクション (元の`base` CTEに相当)
-- =================================================================
base_data AS (
  SELECT
    hon.id AS honkosho_id,
    hon.anken_id,
    an.kohosha_id,
    an.linked_shokikosho_id,
    kgy.tsr_code,
    kgy.name AS company_name,
    -- APsourceを分かりやすいカテゴリに分類
    CASE
      WHEN consts.name = '転機社長名鑑' THEN '転機'
      WHEN consts.name = '人事部経由' THEN '人事部紹介'
      WHEN consts.name IN ('顧問名鑑登録　解放者', '社外取締役名鑑　候補者') THEN '顧問名鑑登録者'
      WHEN consts.name IN ('HP反響', '上場企業役員DM', 'Gアポ') THEN 'その他'
      ELSE consts.name
    END AS ap_source,
    hon.kosho_setteibi,
    -- 日付をYYYY/MM/DD形式にフォーマット
    FORMAT_DATE('%Y/%m/%d', shoki.kosho_setteibi) AS shoki_setteibi_formatted,
    FORMAT_DATE('%Y/%m/%d', shoki.kosho_jisshibi) AS shoki_jisshibi_formatted,
    FORMAT_DATE('%Y/%m/%d', hon.kosho_setteibi) AS hon_setteibi_formatted,
    FORMAT_DATE('%Y/%m/%d', hon.kosho_yoteibi) AS hon_yoteibi_formatted,
    FORMAT_DATE('%Y/%m/%d', hon.kosho_jisshibi) AS hon_jisshibi_formatted,
    COALESCE(syi1.sei_plus, hon.kohosha_tanto) AS kohosha_tanto,
    syi2.sei_plus AS kigyo_tanto,
    cal.Q
  FROM
    `r-group-bigdata.live_rhs.honkoshos` AS hon
    LEFT JOIN `r-group-bigdata.live_rhs.ankens` AS an ON hon.anken_id = an.id
    LEFT JOIN `r-group-bigdata.live_rhs.shokikoshos` AS shoki ON an.linked_shokikosho_id = shoki.id
    LEFT JOIN `r-group-bigdata.live_rhs.kigyos` AS kgy ON an.kigyo_id = kgy.id
    LEFT JOIN `r-group-bigdata.live_rhs.kohoshas` AS khs ON an.kohosha_id = khs.id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi1 ON hon.kohosha_tanto = syi1.user_id
    LEFT JOIN `r-group-bigdata.live_company.syain` AS syi2 ON an.kigyo_tanto = syi2.user_id
    LEFT JOIN calendar_master AS cal ON hon.kosho_setteibi = cal.yyyymmdd
    LEFT JOIN ap_source_master AS consts ON shoki.ap_source = consts.code
  WHERE
    hon.kosho_seq = 1
),

-- =================================================================
-- ランキング付けセクション (元の`HON_SHA` CTEに相当)
-- =================================================================
ranked_data AS (
  SELECT
    *,
    -- 企業(TSRコード)ごと、四半期ごとの交渉順位を計算
    ROW_NUMBER() OVER (PARTITION BY tsr_code, Q ORDER BY kosho_setteibi ASC) AS rn
  FROM
    base_data
)

-- =================================================================
-- 最終的な出力
-- =================================================================
SELECT
  honkosho_id,
  anken_id,
  kohosha_id,
  linked_shokikosho_id,
  tsr_code,
  company_name,
  ap_source,
  shoki_setteibi_formatted AS shoki_setteibi,
  shoki_jisshibi_formatted AS shoki_jisshibi,
  hon_setteibi_formatted AS hon_setteibi,
  hon_yoteibi_formatted AS hon_yoteibi,
  hon_jisshibi_formatted AS hon_jisshibi,
  kohosha_tanto,
  kigyo_tanto,
  Q
FROM
  ranked_data
WHERE
  rn = 1 -- 企業ごと、四半期ごとの最初の交渉のみを抽出
ORDER BY
  kosho_setteibi;
"""

honsha_data = client.query(honsha_data_query).result().to_dataframe()

# %%
selected_honsha_data = honsha_data[honsha_data['hon_setteibi'] >= '2022-10-01']

# %%
koho_shokushu, koho_layer = shokushu_layer_for("kigyo_tanto")
selected_honsha_data = pd.merge(selected_honsha_data, koho_shokushu, on=("Q","kigyo_tanto"), how="left")
selected_honsha_data = pd.merge(selected_honsha_data, koho_layer, on=("Q","kigyo_tanto"), how="left")

# %%
selected_honsha_data = selected_honsha_data[['候担職種','候担レイヤー','tsr_code', 'hon_setteibi', 'Q', 'linked_shokikosho_id','shoki_jisshibi', 'ap_source',
                                             'kigyo_tanto', 'hon_jisshibi']]

# %%
selected_honsha_data = to_sheet_strings(selected_honsha_data, ["linked_shokikosho_id"])

# %%
selected_honsha_data.replace([np.inf, -np.inf], np.nan, inplace=True)
selected_honsha_data.fillna('', inplace=True)

honsha_final = selected_honsha_data.values.tolist()

# %%
SPREADSHEET_ID = '1cy7WA-vAW_51PEpjmPNlo79ZvHB0GSPS0c2D_y9BYDg'
write_to_sheet(SPREADSHEET_ID, 'hon_sha!A', honsha_final)

print("初期交渉→本交渉（件・人・社）のすべての更新が完了しました。")
