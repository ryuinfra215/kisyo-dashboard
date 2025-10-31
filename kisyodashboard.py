# ==========================================================
# 修正済みの result_app.py (インデントとシート読込を修正)
# ==========================================================
import streamlit as st
import gspread
import pandas as pd
import numpy as np
import folium
from folium.plugins import AntPath
from streamlit_folium import st_folium
from google.oauth2.service_account import Credentials

# --- アプリの基本設定 ---
st.set_page_config(page_title="台風コンテスト リアルタイム集計")
st.title("🌪️ 台風進路予想コンテスト リアルタイム集計")

# --- 定数（ここはあなたの設定に合わせてください） ---
# ★★★ あなたのスプレッドシートURLを "..." の部分に入れてください ★★★
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1oO-4cpvAManhT_a5hhAfsLqbPTp9NoAHLWz9sWVY-7Q/edit#gid=662336832" # 例：Colabで使っていたURL

start_lat = 19.8
start_lon = 140.4
seikai_lat_24h = 23.2
seikai_lon_24h = 139.9
seikai_lat_48h = 27.5
seikai_lon_48h = 138.1
seikai_lat_72h = 32.0
seikai_lon_72h = 137.4
seikai_lat_96h = 40.1
seikai_lon_96h = 145.1

# ↓↓↓ インデントを半角スペース4つに修正 ↓↓↓
actual_path = [
    [start_lat, start_lon],
    [seikai_lat_24h, seikai_lon_24h],
    [seikai_lat_48h, seikai_lon_48h],
    [seikai_lat_72h, seikai_lon_72h],
    [seikai_lat_96h, seikai_lon_96h]
]

# --- 距離計算（Colabセル2から） ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(np.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_rad - lon1_rad; dlat = lat2_rad - lat1_rad
    a = np.sin(dlat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

# --- メインの処理（手動更新専用） ---
@st.cache_data 
def load_and_process_data():
    # --- 1. 認証（st.secrets を使う） ---
    scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict_raw = st.secrets["gcp_service_account"]
    creds_dict_fixed = creds_dict_raw.to_dict()
    creds_dict_fixed['private_key'] = creds_dict_fixed['private_key'].replace(r'\\n', '\n').replace(r'\n', '\n')
    creds = Credentials.from_service_account_info(creds_dict_fixed, scopes=scopes)
    gc = gspread.authorize(creds)

    # --- 2. データ読み込み（Colabセル1） ---
    
    # ↓↓↓ シート読み込みを「gid」優先に修正 ↓↓↓
    try:
        spreadsheet = gc.open_by_url(SPREADSHEET_URL)
        gid_str = SPREADSHEET_URL.split('gid=')[-1].split('&')[0]
        worksheet = None
        if gid_str.isdigit():
            worksheet = spreadsheet.get_worksheet_by_id(int(gid_str))
        if worksheet is None:
            worksheet = spreadsheet.worksheet("フォームの回答 1") # GIDが見つからない場合の予備
    except Exception:
        worksheet = gc.open_by_url(SPREADSHEET_URL).sheet1 # 最終手段
    
    rows = worksheet.get_all_values()

    # ↓↓↓ 0件チェックを追加 ↓↓↓
    if len(rows) <= 1:
        empty_cols = [
            '順位', '氏名', '合計誤差(km)', '誤差_24h(km)', 
            '誤差_48h(km)', '誤差_72h(km)', '誤差_96h(km)', 'タイムスタンプ'
        ]
        return pd.DataFrame(columns=empty_cols)

    # Colabで動いた列名（'予想の根拠'）に合わせる
    columns = [
        'タイムスタンプ', '氏名',
        '48時間後の予想緯度（北緯）', '48時間後の予想経度（東経）',
        '予想の根拠', # E列
        '96時間後の予想緯度（北緯）', '96時間後の予想経度（東経）',
        '24時間後の予想緯度（北緯）', '24時間後の予想経度（東経）',
        '72時間後の予想緯度（北緯）', '72時間後の予想経度（東経）'
    ]
    yosou_df = pd.DataFrame(rows[1:], columns=columns)

    # 数値に変換
    num_cols = [col for col in columns if '緯度' in col or '経度' in col]
    for col in num_cols:
        yosou_df[col] = pd.to_numeric(yosou_df[col], errors='coerce')
    yosou_df.dropna(subset=num_cols, inplace=True)

    # --- 3. ランキング計算（Colabセル2） ---
    yosou_df['誤差_24h(km)'] = calculate_distance(yosou_df['24時間後の予想緯度（北緯）'], yosou_df['24時間後の予想経度（東経）'], seikai_lat_24h, seikai_lon_24h)
    yosou_df['誤差_48h(km)'] = calculate_distance(yosou_df['48時間後の予想緯度（北緯）'], yosou_df['48時間後の予想経度（東経）'], seikai_lat_48h, seikai_lon_48h)
    yosou_df['誤差_72h(km)'] = calculate_distance(yosou_df['72時間後の予想緯度（北緯）'], yosou_df['72時間後の予想経度（東経）'], seikai_lat_72h, seikai_lon_72h)
    yosou_df['誤差_96h(km)'] = calculate_distance(yosou_df['96時間後の予想緯度（北緯）'], yosou_df['96時間後の予想経度（東経）'], seikai_lat_96h, seikai_lon_96h)
    
    yosou_df['合計誤差(km)'] = yosou_df['誤差_24h(km)'] + yosou_df['誤差_48h(km)'] + yosou_df['誤差_72h(km)'] + yosou_df['誤差_96h(km)']
    result_df = yosou_df.sort_values(by='合計誤差(km)').round(2).reset_index(drop=True)
    result_df['順位'] = result_df.index + 1
    
    # 「直近の応募者」のためにタイムスタンプ列をコピーしておく
    result_df['タイムスタンプ'] = yosou_df['タイムスタンプ']

    return result_df

# --- アプリの実行 ---
try:
    # 手動更新ボタン
    if st.button("🔄 今すぐ手動で更新"):
        st.cache_data.clear() # キャッシュをクリアして即時更新

    # データをロードして計算
    result_df = load_and_process_data()

    # ↓↓↓ 0件チェックを追加 ↓↓↓
    if result_df.empty:
        st.info("✅ アプリは正常に起動しています。")
        st.info("まだ応募データがありません。最初の応募をお待ちください！")
    else:
        # --- 1. トップ10のランキング ---
        st.subheader("🎉🎉 リアルタイム順位 (Top 10) 🎉🎉")
        display_columns = [
            '順位', '氏名', '合計誤差(km)', 
            '誤差_24h(km)', '誤差_48h(km)', '誤差_72h(km)', '誤差_96h(km)'
        ]
        st.dataframe(
            result_df.head(10)[display_columns],
            use_container_width=True,
            hide_index=True 
        )

        st.divider() 

        # --- 2. 直近の応募者 (最新5名) ---
        st.subheader("✨ 直近の応募者 (最新5名)")
        st.info("応募ありがとうございます！こちらの表で順位をご確認ください。")
        
        recent_df = result_df.sort_values(by='タイムスタンプ', ascending=False)
        
        st.dataframe(
            recent_df.head(5)[display_columns], 
            use_container_width=True,
            hide_index=True 
        )

        # --- マップ作成（全員を表示、1位をハイライト） ---
        st.divider()
        st.subheader("🗺️ 全員の進路予想マップ")
        st.info("現在の1位の経路を赤線で、他の全員の経路をグレーで表示しています。")
        
        # ★★★ 修正点 1: .head(10) を削除し、全員のデータ(result_df)を対象にする ★★★
        map_df = result_df
        
        m = folium.Map(location=[seikai_lat_72h, seikai_lon_72h], zoom_start=5, tiles='CartoDB positron', attribution_control=False)

        # 実際の経路
        AntPath(locations=actual_path, color='black', weight=7, tooltip='実際の経路').add_to(m)
        
        # --- 全員の線の描画 ---
        # ★★★ 修正点 2: ループ対象を map_df (全員) にする ★★★
        for i, row in map_df.reset_index().iterrows(): 
            if i == 0:
                # 1位の人の色
                line_color = 'red'
                line_weight = 5 
            else:
                # 2位以下の人の色
                line_color = 'gray'
                line_weight = 2 

            user_path = [
                [start_lat, start_lon],
                [row['24時間後の予想緯度（北緯）'], row['24時間後の予想経度（東経）']],
                [row['48時間後の予想緯度（北緯）'], row['48時間後の予想経度（東経）']],
                [row['72時間後の予想緯度（北緯）'], row['72時間後の予想経度（東経）']],
                [row['96時間後の予想緯度（北緯）'], row['96時間後の予想経度（東経）']]
            ]
            AntPath(
                locations=user_path, 
                color=line_color, 
                weight=line_weight, 
                tooltip=row['氏名']
            ).add_to(m)

        # スタートとゴールのマーカー
        folium.Marker(location=[start_lat, start_lon], icon=folium.Icon(color='gray', icon='flag-checkered'), popup='スタート').add_to(m)
        folium.Marker(location=actual_path[-1], icon=folium.Icon(color='red', icon='star'), popup='最終到達点').add_to(m)

        # --- 全員のピンの描画 ---
        # ★★★ 修正点 3: ループ対象を map_df (全員) にする ★★★
        for i, row in map_df.reset_index().iterrows():
            if i == 0:
                # 1位の人のピン
                icon_color = 'red'
            else:
                # 2位以下の人のピン
                icon_color = 'gray'
            
            folium.Marker(
                location=[row['96時間後の予想緯度（北緯）'], row['96時間後の予想経度（東経）']],
                icon=folium.Icon(color=icon_color, icon='user'),
                tooltip=f"<strong>{row['順位']}位: {row['氏名']}</strong>",
                popup=f"<strong>{row['順位']}位: {row['氏名']}</strong><br>合計誤差: {row['合計誤差(km)']} km"
            ).add_to(m)
        
        st_folium(m, width='100%', height=500, key="result_map")

# ... (except ブロックは変更なし) ...
except Exception as e:
    # ↓↓↓ ここが切れていた部分です ↓↓↓
    st.error(f"🚨データの読み込み中にエラーが発生しました: {e}")
    st.error("GoogleスプレッドシートのURLや「共有」設定、Streamlitの「Secrets」設定、列名が正しいか確認してください。")
    # デバッグ用に詳細なエラーを表示したい場合は、以下の2行をコメント解除してください
    # import traceback
    # st.exception(traceback.format_exc())