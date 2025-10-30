# ==========================================================
# 修正済みの result_app.py (インデントと列名を修正)
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
# @st.cache_data は「手動更新」ボタンが押されるまで結果を使い回す
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
    worksheet = gc.open_by_url(SPREADSHEET_URL).sheet1
    rows = worksheet.get_all_values()

    # ★★★ ここの列名を、Colabで動いたものと完全に一致させます ★★★
    columns = [
        'タイムスタンプ',                 # A列
        '氏名',                         # B列
        '48時間後の予想緯度（北緯）',         # C列
        '48時間後の予想経度（東経）',         # D列
        '予想の根拠',                   # E列  <- (あれば) を削除！
        '96時間後の予想緯度（北緯）',         # F列
        '96時間後の予想経度（東経）',         # G列
        '24時間後の予想緯度（北緯）',         # H列
        '24時間後の予想経度（東経）',         # I列
        '72時間後の予想緯度（北緯）',         # J列
        '72時間後の予想経度（東経）'          # K列
    ]
    yosou_df = pd.DataFrame(rows[1:], columns=columns)

    # 数値に変換
    num_cols = [col for col in columns if '緯度' in col or '経度' in col]
    for col in num_cols:
        yosou_df[col] = pd.to_numeric(yosou_df[col], errors='coerce')
    yosou_df.dropna(subset=num_cols, inplace=True)

    # --- 3. ランキング計算（Colabセル2） ---
    # ★★★ ここの列名も、Colabで動いたものと一致させます ★★★
    yosou_df['誤差_24h(km)'] = calculate_distance(yosou_df['24時間後の予想緯度（北緯）'], yosou_df['24時間後の予想経度（東経）'], seikai_lat_24h, seikai_lon_24h)
    yosou_df['誤差_48h(km)'] = calculate_distance(yosou_df['48時間後の予想緯度（北緯）'], yosou_df['48時間後の予想経度（東経）'], seikai_lat_48h, seikai_lon_48h)
    yosou_df['誤差_72h(km)'] = calculate_distance(yosou_df['72時間後の予想緯度（北緯）'], yosou_df['72時間後の予想経度（東経）'], seikai_lat_72h, seikai_lon_72h)
    yosou_df['誤差_96h(km)'] = calculate_distance(yosou_df['96時間後の予想緯度（北緯）'], yosou_df['96時間後の予想経度（東経）'], seikai_lat_96h, seikai_lon_96h)
    
    yosou_df['合計誤差(km)'] = yosou_df['誤差_24h(km)'] + yosou_df['誤差_48h(km)'] + yosou_df['誤差_72h(km)'] + yosou_df['誤差_96h(km)']
    result_df = yosou_df.sort_values(by='合計誤差(km)').round(2)

    return result_df

# --- アプリの実行 ---
try:
    # 手動更新ボタン
    if st.button("🔄 今すぐ手動で更新"):
        st.cache_data.clear() # キャッシュをクリアして即時更新

    # データをロードして計算
    result_df = load_and_process_data()

    # --- ランキング表示 (Colabセル2の display) ---
    st.subheader("🎉🎉 リアルタイム順位 🎉🎉")
    st.dataframe(result_df[['氏名', '合計誤差(km)', '誤差_24h(km)', '誤差_48h(km)', '誤差_72h(km)', '誤差_96h(km)']], use_container_width=True)

    # --- マップ作成（Colabセル3） ---
    st.subheader("🗺️ 全員の進路予想マップ")
    m = folium.Map(location=[seikai_lat_72h, seikai_lon_72h], zoom_start=5, tiles='CartoDB positron', attribution_control=False)
    colors = ['blue', 'green', 'purple', 'orange', 'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue']

    AntPath(locations=actual_path, color='black', weight=7, tooltip='実際の経路').add_to(m)

    for i, row in result_df.iterrows():
        user_color = colors[i % len(result_df)]
        user_path = [
            [start_lat, start_lon],
            [row['24時間後の予想緯度（北緯）'], row['24時間後の予想経度（東経）']],
            [row['48時間後の予想緯度（北緯）'], row['48時間後の予想経度（東経）']],
            [row['72時間後の予想緯度（北緯）'], row['72時間後の予想経度（東経）']],
            [row['96時間後の予想緯度（北緯）'], row['96時間後の予想経度（東経）']]
        ]
        AntPath(locations=user_path, color=user_color, weight=3, tooltip=row['氏名']).add_to(m)

    folium.Marker(location=[start_lat, start_lon], icon=folium.Icon(color='gray', icon='flag-checkered'), popup='スタート').add_to(m)
    folium.Marker(location=actual_path[-1], icon=folium.Icon(color='red', icon='star'), popup='最終到達点').add_to(m)

    st_folium(m, width='100%', height=500, key="result_map")

except Exception as e:
    st.error(f"🚨データの読み込み中にエラーが発生しました: {e}")
    st.error("GoogleスプレッドシートのURLや「共有」設定、Streamlitの「Secrets」設定を見直してください。")