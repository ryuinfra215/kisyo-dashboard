# ==========================================================
# 最終修正版 result_app.py
# ==========================================================
import streamlit as st
import gspread
import pandas as pd
import numpy as np
import folium
from folium.plugins import AntPath # AntPathは実際の経路にだけ使う
from streamlit_folium import st_folium
from google.oauth2.service_account import Credentials

# --- アプリの基本設定 ---
st.set_page_config(page_title="台風コンテスト リアルタイム集計",layout="wide")
st.title("🌪️ 台風進路予想コンテスト リアルタイム集計")
# 名前を複数入れたいので、リスト（[]）で初期化します
if 'selected_names' not in st.session_state:
    st.session_state.selected_names = []

# --- 定数 ---
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1oO-4cpvAManhT_a5hhAfsLqbPTp9NoAHLWz9sWVY-7Q/edit#gid=662336832" # あなたのURL
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

# --- 距離計算 ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(np.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_rad - lon1_rad; dlat = lat2_rad - lat1_rad
    a = np.sin(dlat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

# --- メインの処理（手動更新専用） ---
# ==========================================================
# 修正版の load_and_process_data 関数
# ==========================================================
@st.cache_data 
def load_and_process_data():
    # --- 1. 認証 ---
    scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict_raw = st.secrets["gcp_service_account"]
    
    # st.secrets が to_dict() をサポートしていない場合のフォールバック
    if hasattr(creds_dict_raw, 'to_dict'):
        creds_dict_fixed = creds_dict_raw.to_dict()
    else:
        creds_dict_fixed = dict(creds_dict_raw)
        
    creds_dict_fixed['private_key'] = creds_dict_fixed['private_key'].replace(r'\\n', '\n').replace(r'\n', '\n')
    creds = Credentials.from_service_account_info(creds_dict_fixed, scopes=scopes)
    gc = gspread.authorize(creds)

    # --- 2. データ読み込み（gid優先） ---
    try:
        spreadsheet = gc.open_by_url(SPREADSHEET_URL)
        gid_str = SPREADSHEET_URL.split('gid=')[-1].split('&')[0]
        worksheet = None
        if gid_str.isdigit():
            worksheet = spreadsheet.get_worksheet_by_id(int(gid_str))
        if worksheet is None:
            worksheet = spreadsheet.worksheet("フォームの回答 1") # デフォルト名
    except Exception:
        worksheet = gc.open_by_url(SPREADSHEET_URL).sheet1
    
    rows = worksheet.get_all_values()

    # --- 0件チェック ---
    if len(rows) <= 1:
        empty_cols = ['順位', '名前', '合計誤差(km)', '誤差_24h(km)', '誤差_48h(km)', '誤差_72h(km)', '誤差_96h(km)', 'タイムスタンプ']
        return pd.DataFrame(columns=empty_cols), pd.DataFrame(columns=empty_cols)

    # --- 列の定義 ---
    columns = [
        'タイムスタンプ', '名前',
        '48時間後の予想緯度（北緯）', '48時間後の予想経度（東経）',
        '予想の根拠', # E列
        '96時間後の予想緯度（北緯）', '96時間後の予想経度（東経）',
        '24時間後の予想緯度（北緯）', '24時間後の予想経度（東経）',
        '72時間後の予想緯度（北緯）', '72時間後の予想経度（東経）'
    ]
    yosou_df = pd.DataFrame(rows[1:], columns=columns)

    # --- データ整形 ---
    num_cols = [col for col in columns if '緯度' in col or '経度' in col]
    for col in num_cols:
        yosou_df[col] = pd.to_numeric(yosou_df[col], errors='coerce')
    yosou_df.dropna(subset=num_cols, inplace=True)
    yosou_df['名前'] = yosou_df['名前'].replace('', '（未入力）')

    # --- ★★★ ここから修正 ★★★ ---
    # タイムスタンプを日付時刻型に変換（これがソートに必要）
    # 形式が "YYYY/MM/DD HH:MM:SS" でない場合、エラーになる可能性がある
    try:
        yosou_df['タイムスタンプ_dt'] = pd.to_datetime(yosou_df['タイムスタンプ'])
    except Exception:
        # 形式が異なる場合のフォールバック（例: MM/DD/YYYY）
        yosou_df['タイムスタンプ_dt'] = pd.to_datetime(yosou_df['タイムスタンプ'], errors='coerce')

    # --- ランキング計算 ---
    yosou_df['誤差_24h(km)'] = calculate_distance(yosou_df['24時間後の予想緯度（北緯）'], yosou_df['24時間後の予想経度（東経）'], seikai_lat_24h, seikai_lon_24h)
    yosou_df['誤差_48h(km)'] = calculate_distance(yosou_df['48時間後の予想緯度（北緯）'], yosou_df['48時間後の予想経度（東経）'], seikai_lat_48h, seikai_lon_48h)
    yosou_df['誤差_72h(km)'] = calculate_distance(yosou_df['72時間後の予想緯度（北緯）'], yosou_df['72時間後の予想経度（東経）'], seikai_lat_72h, seikai_lon_72h)
    yosou_df['誤差_96h(km)'] = calculate_distance(yosou_df['96時間後の予想緯度（北緯）'], yosou_df['96時間後の予想経度（東経）'], seikai_lat_96h, seikai_lon_96h)
    yosou_df['合計誤差(km)'] = yosou_df['誤差_24h(km)'] + yosou_df['誤差_48h(km)'] + yosou_df['誤差_72h(km)'] + yosou_df['誤差_96h(km)']
    
    # --- 1. 順位順のDF (result_df) を作成 ---
    result_df = yosou_df.sort_values(by='合計誤差(km)').reset_index(drop=True)
    result_df['順位'] = result_df.index + 1
    
    # --- 2. タイムスタンプ順のDF (recent_df) を作成 ---
    # result_df (誤差順) ではなく、yosou_df (元の順序) をベースにする
    
    # yosou_df に「順位」情報をマージ（結合）する
    # result_df から必要な列だけ（順位、名前、タイムスタンプ）を抽出
    rank_info = result_df[['名前', 'タイムスタンプ', '順位']]
    
    # yosou_df (元の時系列順) に順位情報をマージ
    merged_df = pd.merge(yosou_df, rank_info, on=['名前', 'タイムスタンプ'], how='left')
    
    # タイムスタンプ（datetimeオブジェクト）で降順ソート（最新が上）
    recent_df = merged_df.sort_values(by='タイムスタンプ_dt', ascending=False)
    
    # 不要な列を削除
    if 'タイムスタンプ_dt' in result_df.columns:
        result_df = result_df.drop(columns=['タイムスタンプ_dt'])
    if 'タイムスタンプ_dt' in recent_df.columns:
        recent_df = recent_df.drop(columns=['タイムスタンプ_dt'])

    return result_df, recent_df # 2つ返す
# ==========================================================
# --- アプリの実行 ---
try:
    # 手動更新ボタン
    if st.button("🔄 今すぐ手動で更新"):
        st.cache_data.clear() # キャッシュをクリアして即時更新
        st.session_state.selected_name = None
    # データをロードして計算
    result_df, recent_df = load_and_process_data()

    if result_df.empty:
        st.info("✅ アプリは正常に起動しています。")
        st.info("まだ応募データがありません。最初の応募をお待ちください！")
    else:
        format_dict = {
            '合計誤差(km)': "{:.0f}",
            '誤差_24h(km)': "{:.0f}",
            '誤差_48h(km)': "{:.0f}",
            '誤差_72h(km)': "{:.0f}",
            '誤差_96h(km)': "{:.0f}"
        }
        header_style = [{'selector': 'th', 'props': [('text-align', 'center')]}]
        # --- ★★★ ここからレイアウト修正 ★★★ ---
        # 画面を 2:3 の比率で2列に分割
        col1, col2 = st.columns([2, 3])
        
        # --- col1 (左側) にランキングを表示 ---
        # --- col1 (左側) にランキングを表示 ---
        with col1:
            table_styles = [
                {'selector': 'th, td', 'props': [('text-align', 'center')]} 
            ]
            
            # --- 1. トップ10のランキング ---
            st.subheader("🎉リアルタイム順位 (Top 3)🎉")
            display_columns = [
                '順位', '名前', '合計誤差(km)', 
            ]
            st.dataframe(
                result_df.head(3)[display_columns].style.format({'合計誤差(km)': "{:.2f}"}).set_table_styles(table_styles),
                width='stretch',
                hide_index=True 
            )

            st.divider() 

            # --- 2. 直近の応募者 (最新5名) ---
            st.subheader("✨ 直近の応募者 (最新5名)")
            st.info(f"現在の参加者数は{len(result_df['合計誤差(km)'])}人です！")
            
            # 選択解除ボタン（リストを空にする）
            if st.button("マップの選択を解除"):
                st.session_state.selected_names = []
                st.rerun()
             
            display_columns_recent= [
                '順位', '名前', '合計誤差(km)', '誤差_24h(km)', '誤差_48h(km)', '誤差_72h(km)', '誤差_96h(km)',
            ]

            # ★ここが修正ポイント：表示件数とターゲットDFを一致させる
            target_recent_df = recent_df.head(5)

            st.dataframe(
                target_recent_df[display_columns_recent]
                    .style
                    .format(format_dict)
                    .set_properties(**{'text-align': 'center'})
                    .set_table_styles(header_style),
                width='stretch',
                hide_index=True,
                on_select="rerun", 
                selection_mode="multi-row", # ★ここを「multi-row」に変更
                key="recent_table" 
            )
            
            # ★ここが修正ポイント：複数人の名前を取得してリストに保存
            selection = st.session_state.get('recent_table', {}).get('selection', {})
            if selection:
                selected_indices = selection.get('rows', [])
                if selected_indices:
                    # 選択された行インデックスに対応する「名前」をリストとして取得
                    selected_names_list = target_recent_df.iloc[selected_indices]['名前'].tolist()
                    st.session_state.selected_names = selected_names_list
                else:
                    # 行選択が外された場合（手動でチェックを外した時など）
                    st.session_state.selected_names = []
        

        # --- col2 (右側) にマップを表示 ---
        with col2:
            st.subheader("🗺️**進路予想マップ**")
            st.markdown("<small>1位:赤、最新:青、選択中:紫(破線)、その他:グレー</small>", unsafe_allow_html=True)
            
            map_df = result_df
            
            # 1位と最新の応募者の行データを取得
            winner_row = result_df.iloc[0]
            latest_row = recent_df.iloc[0]
            winner_name = winner_row['名前']
            latest_name = latest_row['名前']

            # ★変更: session_state から「選択された名前リスト」を取得
            selected_names_list = st.session_state.selected_names

            m = folium.Map(location=[seikai_lat_72h, seikai_lon_72h], zoom_start=5, tiles='OpenStreetMap', attribution_control=False)
            
            # 描画順 1: 「その他全員（グレー）」
            for i, row in map_df.iterrows():
                # ★変更: 名前が「選択されたリスト」に含まれていない場合のみグレーで描画
                if (row['名前'] != winner_name and 
                    row['名前'] != latest_name and 
                    row['名前'] not in selected_names_list): 
                    
                    user_path = [
                        [start_lat, start_lon],
                        [row['24時間後の予想緯度（北緯）'], row['24時間後の予想経度（東経）']],
                        [row['48時間後の予想緯度（北緯）'], row['48時間後の予想経度（東経）']],
                        [row['72時間後の予想緯度（北緯）'], row['72時間後の予想経度（東経）']],
                        [row['96時間後の予想緯度（北緯）'], row['96時間後の予想経度（東経）']]
                    ]
                    folium.PolyLine(locations=user_path, color='gray', weight=2, tooltip=row['名前']).add_to(m)

            # 描画順 2: 「実際の経路（黒）」
            AntPath(locations=actual_path, color='black', weight=7, tooltip='実際の経路').add_to(m)

            # 描画順 3: 「1位の経路（赤）」
            # 選択リストに含まれていても、1位なら赤を優先して描画
            if winner_name not in selected_names_list:
                winner_path = [
                    [start_lat, start_lon],
                    [winner_row['24時間後の予想緯度（北緯）'], winner_row['24時間後の予想経度（東経）']],
                    [winner_row['48時間後の予想緯度（北緯）'], winner_row['48時間後の予想経度（東経）']],
                    [winner_row['72時間後の予想緯度（北緯）'], winner_row['72時間後の予想経度（東経）']],
                    [winner_row['96時間後の予想緯度（北緯）'], winner_row['96時間後の予想経度（東経）']]
                ]
                folium.PolyLine(locations=winner_path, color='red', weight=5, tooltip=winner_row['名前']).add_to(m)

            # 描画順 4: 「最新の経路（青）」
            if latest_name not in selected_names_list:
                latest_path=[
                    [start_lat, start_lon],
                    [latest_row['24時間後の予想緯度（北緯）'], latest_row['24時間後の予想経度（東経）']],
                    [latest_row['48時間後の予想緯度（北緯）'], latest_row['48時間後の予想経度（東経）']],
                    [latest_row['72時間後の予想緯度（北緯）'], latest_row['72時間後の予想経度（東経）']],
                    [latest_row['96時間後の予想緯度（北緯）'], latest_row['96時間後の予想経度（東経）']]
                ]
                folium.PolyLine(locations=latest_path, color='blue', weight=5, tooltip=latest_row['名前']).add_to(m)
            
            # ★変更: 選択中の人（複数）をループして描画
            if selected_names_list:
                for name in selected_names_list:
                    # 名前でデータを検索
                    person_rows = result_df[result_df['名前'] == name]
                    if not person_rows.empty:
                        person_data = person_rows.iloc[0]
                        
                        selected_path = [
                            [start_lat, start_lon],
                            [person_data['24時間後の予想緯度（北緯）'], person_data['24時間後の予想経度（東経）']],
                            [person_data['48時間後の予想緯度（北緯）'], person_data['48時間後の予想経度（東経）']],
                            [person_data['72時間後の予想緯度（北緯）'], person_data['72時間後の予想経度（東経）']],
                            [person_data['96時間後の予想緯度（北緯）'], person_data['96時間後の予想経度（東経）']]
                        ]
                        # 紫色の破線
                        folium.PolyLine(locations=selected_path, color='purple', weight=6, dash_array='5, 5', 
                                        tooltip=f"選択中: {person_data['名前']}").add_to(m)


            # マーカー（ピン）の描画
            folium.Marker(location=[start_lat, start_lon], icon=folium.Icon(color='gray', icon='flag-checkered'), popup='スタート').add_to(m)
            folium.Marker(location=actual_path[-1], icon=folium.Icon(color='red', icon='flag'), popup='最終到達点').add_to(m)

            # 1位と最新にはマーカーを表示
            folium.Marker(
                location=[winner_row['96時間後の予想緯度（北緯）'], winner_row['96時間後の予想経度（東経）']],
                icon=folium.Icon(color='red', icon='user'),
                tooltip=f"<strong>{winner_row['順位']}位: {winner_row['名前']}</strong>",
                popup=f"<strong>{winner_row['順位']}位: {winner_row['名前']}</strong><br>合計誤差: {winner_row['合計誤差(km)']} km"
            ).add_to(m)
            
            if winner_name != latest_name:
                folium.Marker(
                    location=[latest_row['96時間後の予想緯度（北緯）'], latest_row['96時間後の予想経度（東経）']],
                    icon=folium.Icon(color='blue', icon='user'),
                    tooltip=f"<strong>{latest_row['順位']}位 (最新): {latest_row['名前']}</strong>",
                    popup=f"<strong>{latest_row['順位']}位 (最新): {latest_row['名前']}</strong><br>合計誤差: {latest_row['合計誤差(km)']} km"
                ).add_to(m)
            
            st_folium(m, width='100%', height=800, key="result_map")

except Exception as e:
    st.error(f"🚨データの読み込み中にエラーが発生しました: {e}")
    st.error("GoogleスプレッドシートのURLや「共有」設定、Streamlitの「Secrets」設定、列名が正しいか確認してください。")
    import traceback
    st.exception(traceback.format_exc())