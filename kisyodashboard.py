# ==========================================================
# 最終統合版 result_app.py (管理者認証・締め切り制御付き)
# ==========================================================
import streamlit as st
import gspread
import pandas as pd
import numpy as np
import folium
import time
from folium.plugins import AntPath, BeautifyIcon
from streamlit_folium import st_folium
from google.oauth2.service_account import Credentials

# --- 認証定数 ---
# ★★★★ ここを秘密のパスワードに変更してください ★★★★
ADMIN_PASSWORD = "made2025_kisyo"
# ★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★

# --- アプリの基本設定 ---
st.set_page_config(page_title="台風コンテスト リアルタイム集計", layout="wide")
st.title("🌪️ 台風進路予想コンテスト リアルタイム集計")

# --- 認証状態と締め切り状態の初期化 ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'is_closed' not in st.session_state:
    st.session_state.is_closed = False
if 'selected_names' not in st.session_state:
    st.session_state.selected_names = []
if 'update_start_time' not in st.session_state:
    st.session_state.update_start_time = 0


# --- 認証関数 ---
def authenticate_user():
    """パスワード認証を行う関数"""
    st.sidebar.title("管理者ログイン")
    password = st.sidebar.text_input("パスワードを入力", type="password")
    
    if st.sidebar.button("ログイン"):
        if password == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.sidebar.error("パスワードが違います")


# 🔥 認証チェック (未ログインならここで実行停止) 🔥
if not st.session_state.authenticated:
    authenticate_user()
    st.stop()
# -----------------------------
# ログイン成功後はここから実行されます


# --- 定数 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1oO-4cpvAManhT_a5hhAfsLqbPTp9NoAHLWz9sWVY-7Q/edit#gid=662336832"
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

# --- 距離計算 (既存) ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(np.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_rad - lon1_rad; dlat = lat2_rad - lat1_rad
    a = np.sin(dlat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

# --- データ取得関数 (既存) ---
@st.cache_data 
def load_and_process_data():
    # 認証 (既存ロジック)
    scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict_raw = st.secrets["gcp_service_account"]
    
    if hasattr(creds_dict_raw, 'to_dict'):
        creds_dict_fixed = creds_dict_raw.to_dict()
    else:
        creds_dict_fixed = dict(creds_dict_raw)
        
    creds_dict_fixed['private_key'] = creds_dict_fixed['private_key'].replace(r'\\n', '\n').replace(r'\n', '\n')
    creds = Credentials.from_service_account_info(creds_dict_fixed, scopes=scopes)
    gc = gspread.authorize(creds)

    # データ読み込みとランキング計算 (既存ロジック)
    try:
        spreadsheet = gc.open_by_url(SPREADSHEET_URL)
        gid_str = SPREADSHEET_URL.split('gid=')[-1].split('&')[0]
        worksheet = None
        if gid_str.isdigit():
            worksheet = spreadsheet.get_worksheet_by_id(int(gid_str))
        if worksheet is None:
            worksheet = spreadsheet.worksheet("フォームの回答 1")
    except Exception:
        worksheet = gc.open_by_url(SPREADSHEET_URL).sheet1
    
    rows = worksheet.get_all_values()

    if len(rows) <= 1:
        empty_cols = ['順位', '名前', '合計誤差(km)', '誤差_24h(km)', '誤差_48h(km)', '誤差_72h(km)', '誤差_96h(km)', 'タイムスタンプ']
        return pd.DataFrame(columns=empty_cols), pd.DataFrame(columns=empty_cols)

    columns = [
        'タイムスタンプ', '名前',
        '48時間後の予想緯度（北緯）', '48時間後の予想経度（東経）',
        '予想の根拠', 
        '96時間後の予想緯度（北緯）', '96時間後の予想経度（東経）',
        '24時間後の予想緯度（北緯）', '24時間後の予想経度（東経）',
        '72時間後の予想緯度（北緯）', '72時間後の予想経度（東経）'
    ]
    yosou_df = pd.DataFrame(rows[1:], columns=columns)

    num_cols = [col for col in columns if '緯度' in col or '経度' in col]
    for col in num_cols:
        yosou_df[col] = pd.to_numeric(yosou_df[col], errors='coerce')
    yosou_df.dropna(subset=num_cols, inplace=True)
    yosou_df['名前'] = yosou_df['名前'].replace('', '（未入力）')

    try:
        yosou_df['タイムスタンプ_dt'] = pd.to_datetime(yosou_df['タイムスタンプ'])
    except Exception:
        yosou_df['タイムスタンプ_dt'] = pd.to_datetime(yosou_df['タイムスタンプ'], errors='coerce')

    # ランキング計算 (既存ロジック)
    yosou_df['誤差_24h(km)'] = calculate_distance(yosou_df['24時間後の予想緯度（北緯）'], yosou_df['24時間後の予想経度（東経）'], seikai_lat_24h, seikai_lon_24h)
    yosou_df['誤差_48h(km)'] = calculate_distance(yosou_df['48時間後の予想緯度（北緯）'], yosou_df['48時間後の予想経度（東経）'], seikai_lat_48h, seikai_lon_48h)
    yosou_df['誤差_72h(km)'] = calculate_distance(yosou_df['72時間後の予想緯度（北緯）'], yosou_df['72時間後の予想経度（東経）'], seikai_lat_72h, seikai_lon_72h)
    yosou_df['誤差_96h(km)'] = calculate_distance(yosou_df['96時間後の予想緯度（北緯）'], yosou_df['96時間後の予想経度（東経）'], seikai_lat_96h, seikai_lon_96h)
    yosou_df['合計誤差(km)'] = yosou_df['誤差_24h(km)'] + yosou_df['誤差_48h(km)'] + yosou_df['誤差_72h(km)'] + yosou_df['誤差_96h(km)']
    
    result_df = yosou_df.sort_values(by='合計誤差(km)').reset_index(drop=True)
    result_df['順位'] = result_df.index + 1
    
    rank_info = result_df[['名前', 'タイムスタンプ', '順位']]
    merged_df = pd.merge(yosou_df, rank_info, on=['名前', 'タイムスタンプ'], how='left')
    recent_df = merged_df.sort_values(by='タイムスタンプ_dt', ascending=False)
    
    if 'タイムスタンプ_dt' in result_df.columns:
        result_df = result_df.drop(columns=['タイムスタンプ_dt'])
    if 'タイムスタンプ_dt' in recent_df.columns:
        recent_df = recent_df.drop(columns=['タイムスタンプ_dt'])

    return result_df, recent_df

# ==========================================================
# --- アプリの実行 ---
try:
    # データをロードして計算
    result_df, recent_df = load_and_process_data()

    # 🔥 運営者操作パネル 🔥
    st.divider()
    st.subheader("🔑 運営者操作パネル (ログイン済み)")

    col_close, col_open, col_refresh = st.columns(3)

    # 締め切りボタン
    with col_close:
        if st.button("🚨 予想受付を締め切り、正解を表示する", type="primary", use_container_width=True):
            st.session_state.is_closed = True
            st.cache_data.clear() # キャッシュをクリアし、全員に反映
            st.rerun()
            
    # 予想受付再開ボタン
    with col_open:
        if st.button("✅ 予想受付を再開する", type="secondary", use_container_width=True):
            st.session_state.is_closed = False
            st.cache_data.clear()
            st.rerun()

    # データ更新ボタン
    with col_refresh:
        if st.button("🔄 データ更新 (全員に反映)", type="secondary", use_container_width=True):
            st.cache_data.clear()
            st.session_state.selected_names = []
            st.session_state.update_start_time = time.time()
            st.rerun()

    # 締め切り状態の通知
    if st.session_state.is_closed:
         st.warning("⚠️ 予想受付は締め切られ、真の進路が表示されています。")
    else:
         st.info("📣 予想受付中です。真の進路は表示されていません。")

    st.divider()
    # 🔥 パネル終了 🔥


    if result_df.empty:
        st.info("✅ アプリは正常に起動しています。")
        st.info("まだ応募データがありません。最初の応募をお待ちください！")
    else:
        format_dict = {
            '合計誤差(km)': "{:.0f}", '誤差_24h(km)': "{:.0f}", '誤差_48h(km)': "{:.0f}", '誤差_72h(km)': "{:.0f}", '誤差_96h(km)': "{:.0f}"
        }
        header_style = [{'selector': 'th', 'props': [('text-align', 'center')]}]
        
        col1, col2 = st.columns([2, 3])
        
        # --- col1 (ランキング) --- (既存ロジック)
        with col1:
            table_styles = [{'selector': 'th, td', 'props': [('text-align', 'center')]}]
            
            st.subheader("🎉リアルタイム順位 (Top 3)🎉")
            display_columns = ['順位', '名前', '合計誤差(km)']
            st.dataframe(result_df.head(3)[display_columns].style.format({'合計誤差(km)': "{:.2f}"}).set_table_styles(table_styles), width='stretch', hide_index=True)

            st.divider() 

            st.subheader("✨ 直近の応募者 (最新5名)")
            st.info(f"現在の参加者数は{len(result_df['合計誤差(km)'])}人です！")
            
            if st.button("マップの選択を解除"):
                st.session_state.selected_names = []
                st.rerun()
            
            display_columns_recent= ['順位', '名前', '合計誤差(km)', '誤差_24h(km)', '誤差_48h(km)', '誤差_72h(km)', '誤差_96h(km)']
            target_recent_df = recent_df.head(5)

            st.dataframe(
                target_recent_df[display_columns_recent].style.format(format_dict).set_properties(**{'text-align': 'center'}).set_table_styles(header_style),
                width='stretch', hide_index=True, on_select="rerun", selection_mode="multi-row", key="recent_table" 
            )
            
            selection = st.session_state.get('recent_table', {}).get('selection', {})
            if selection:
                selected_indices = selection.get('rows', [])
                if selected_indices:
                    selected_names_list = target_recent_df.iloc[selected_indices]['名前'].tolist()
                    st.session_state.selected_names = selected_names_list
                else:
                    st.session_state.selected_names = []

        # --- col2 (マップ) --- (既存ロジックを修正)
        with col2:
            st.subheader("🗺️**進路予想マップ**")
            
            timer_placeholder = st.empty()
            elapsed_time = time.time() - st.session_state.update_start_time
            # ライン表示の制御は、締め切り状態にも依存させる (締め切り後は常時表示が望ましい)
            show_lines = st.session_state.is_closed or (elapsed_time < 120) 
            
            if not show_lines and not st.session_state.is_closed:
                timer_placeholder.caption("🔒 表示時間が終了しました（更新ボタンで再表示）")
            
            st.markdown("<small>1位:赤、最新:青、選択中:紫(破線)、その他:濃いグレー</small>", unsafe_allow_html=True)
            
            map_df = result_df
            winner_row = result_df.iloc[0]
            latest_row = recent_df.iloc[0]
            winner_name = winner_row['名前']
            latest_name = latest_row['名前']
            selected_names_list = st.session_state.selected_names

            # 地図作成
            m = folium.Map(location=[seikai_lat_72h, seikai_lon_72h], zoom_start=5, tiles='OpenStreetMap', attribution_control=False)
            
            # 共通マーカー (スタート地点)
            folium.Marker(location=[start_lat, start_lon], icon=folium.Icon(color='gray', icon='flag-checkered'), popup='スタート').add_to(m)


            # 🔥 真の進路の描画は、締め切り後のみ 🔥
            if st.session_state.is_closed:
                # 実際の経路 (黒)
                AntPath(locations=actual_path, color='black', weight=7, tooltip='実際の経路').add_to(m)

                # 正解ポイントのマーカー
                correct_points = [
                    {"num": 24, "lat": seikai_lat_24h, "lon": seikai_lon_24h},
                    {"num": 48, "lat": seikai_lat_48h, "lon": seikai_lon_48h},
                    {"num": 72, "lat": seikai_lat_72h, "lon": seikai_lon_72h},
                    {"num": 96, "lat": seikai_lat_96h, "lon": seikai_lon_96h},
                ]
                for pt in correct_points:
                    icon = BeautifyIcon(
                        number=pt["num"],
                        border_color='black', # 枠線の色
                        text_color='black', 
                        background_color='#FFF',
                        inner_icon_style='font-size:12px;font-weight:bold;'
                    )
                    folium.Marker(
                        [pt["lat"], pt["lon"]],
                        icon=icon,
                        tooltip=f"正解: {pt['num']}時間後"
                    ).add_to(m)


            # --- 応募者の予想ライン描画 ---
            if show_lines: 
                # その他 (グレー)
                for i, row in map_df.iterrows():
                    # 1位、最新、選択中ではない場合
                    if (row['名前'] != winner_name and row['名前'] != latest_name and row['名前'] not in selected_names_list): 
                        user_path = [
                            [start_lat, start_lon], [row['24時間後の予想緯度（北緯）'], row['24時間後の予想経度（東経）']],
                            [row['48時間後の予想緯度（北緯）'], row['48時間後の予想経度（東経）']], [row['72時間後の予想緯度（北緯）'], row['72時間後の予想経度（東経）']],
                            [row['96時間後の予想緯度（北緯）'], row['96時間後の予想経度（東経）']]
                        ]
                        folium.PolyLine(locations=user_path, color='#555555', weight=3, opacity=0.6, tooltip=row['名前']).add_to(m)

                # 1位 (赤)
                if winner_name not in selected_names_list:
                    winner_path = [
                        [start_lat, start_lon], [winner_row['24時間後の予想緯度（北緯）'], winner_row['24時間後の予想経度（東経）']],
                        [winner_row['48時間後の予想緯度（北緯）'], winner_row['48時間後の予想経度（東経）']], [winner_row['72時間後の予想緯度（北緯）'], winner_row['72時間後の予想経度（東経）']],
                        [winner_row['96時間後の予想緯度（北緯）'], winner_row['96時間後の予想経度（東経）']]
                    ]
                    folium.PolyLine(locations=winner_path, color='red', weight=5, tooltip=winner_row['名前']).add_to(m)

                # 最新 (青)
                if latest_name not in selected_names_list:
                    latest_path=[
                        [start_lat, start_lon], [latest_row['24時間後の予想緯度（北緯）'], latest_row['24時間後の予想経度（東経）']],
                        [latest_row['48時間後の予想緯度（北緯）'], latest_row['48時間後の予想経度（東経）']], [latest_row['72時間後の予想緯度（北緯）'], latest_row['72時間後の予想経度（東経）']],
                        [latest_row['96時間後の予想緯度（北緯）'], latest_row['96時間後の予想経度（東経）']]
                    ]
                    folium.PolyLine(locations=latest_path, color='blue', weight=5, tooltip=latest_row['名前']).add_to(m)
                
                # 選択中 (紫)
                if selected_names_list:
                    for name in selected_names_list:
                        person_rows = result_df[result_df['名前'] == name]
                        if not person_rows.empty:
                            person_data = person_rows.iloc[0]
                            selected_path = [
                                [start_lat, start_lon], [person_data['24時間後の予想緯度（北緯）'], person_data['24時間後の予想経度（東経）']],
                                [person_data['48時間後の予想緯度（北緯）'], person_data['48時間後の予想経度（東経）']], [person_data['72時間後の予想緯度（北緯）'], person_data['72時間後の予想経度（東経）']],
                                [person_data['96時間後の予想緯度（北緯）'], person_data['96時間後の予想経度（東経）']]
                            ]
                            folium.PolyLine(locations=selected_path, color='purple', weight=6, dash_array='5, 5', tooltip=f"選択中: {person_data['名前']}").add_to(m)

                # マーカー (96h後の予想終点のみ)
                folium.Marker(location=[winner_row['96時間後の予想緯度（北緯）'], winner_row['96時間後の予想経度（東経）']], icon=folium.Icon(color='red', icon='user'), tooltip=f"<strong>{winner_row['順位']}位: {winner_row['名前']}</strong>", popup=f"<strong>{winner_row['順位']}位: {winner_row['名前']}</strong><br>合計誤差: {winner_row['合計誤差(km)']} km").add_to(m)
                if winner_name != latest_name:
                    folium.Marker(location=[latest_row['96時間後の予想緯度（北緯）'], latest_row['96時間後の予想経度（東経）']], icon=folium.Icon(color='blue', icon='user'), tooltip=f"<strong>{latest_row['順位']}位 (最新): {latest_row['名前']}</strong>", popup=f"<strong>{latest_row['順位']}位 (最新): {latest_row['名前']}</strong><br>合計誤差: {latest_row['合計誤差(km)']} km").add_to(m)


            # 地図描画
            st_folium(m, width='100%', height=800, key="result_map")

            # --- カウントダウン処理 --- (既存ロジック)
            if show_lines and not st.session_state.is_closed:
                remaining_seconds = int(120 - elapsed_time)
                for i in range(remaining_seconds, -1, -1):
                    timer_placeholder.caption(f"⏳ 結果表示中... あと {i} 秒でラインが非表示になります")
                    time.sleep(1)
                st.rerun()

except Exception as e:
    st.error(f"🚨データの読み込み中にエラーが発生しました: {e}")
    st.error("GoogleスプレッドシートのURLや「共有」設定、Streamlitの「Secrets」設定、列名が正しいか確認してください。")
    import traceback
    st.exception(traceback.format_exc())