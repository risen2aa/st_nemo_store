import streamlit as st
import pandas as pd
import sqlite3
import os
import plotly.express as px
import json
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# 페이지 설정
st.set_page_config(
    page_title="Nemostore 상가 대시보드",
    page_icon="🏪",
    layout="wide"
)

# 세션 상태 초기화 (필터 및 선택)
if "selected_item_id" not in st.session_state:
    st.session_state.selected_item_id = None
if "reset" not in st.session_state:
    st.session_state.reset = False

def reset_filters():
    for key in ['search_text', 'biz_select', 'dep_slider', 'rent_slider']:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.selected_item_id = None

# 갤러리 상세보기 클릭 처리기
def select_item(item_id):
    st.session_state.selected_item_id = item_id

def deselect_item():
    st.session_state.selected_item_id = None

# 금액 포맷터 유틸리티 함수
def format_currency(amount_in_10k):
    if pd.isna(amount_in_10k) or amount_in_10k == 0:
        return "없음"
    amount = int(amount_in_10k)
    if amount >= 10000:
        uk = amount // 10000
        man = amount % 10000
        if man > 0:
            return f"{uk}억 {man:,}만원"
        else:
            return f"{uk}억원"
    else:
        return f"{amount:,}만원"

# 역 이름 좌표 매핑 내부 데이터 (주로 쓰이는 역들 캐싱)
STATION_COORDS = {
    '을지로입구역': (37.5660, 126.9827),
    '종로3가역': (37.5704, 126.9921),
    '경복궁역': (37.5758, 126.9734),
    '종각역': (37.5702, 126.9830),
    '광화문역': (37.5710, 126.9769),
    '명동역': (37.5610, 126.9863),
    '시청역': (37.5657, 126.9772),
    '안국역': (37.5765, 126.9854),
    '을지로3가역': (37.5663, 126.9918),
    '을지로4가역': (37.5666, 126.9980),
    '동대문역': (37.5714, 127.0096)
}

# 데이터 로딩
@st.cache_data(ttl=3600)
def load_data():
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'nemostore.db')
    conn = sqlite3.connect(db_path)
    
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall() if t[0] != 'sqlite_sequence']
    table_name = tables[0] if tables else None
            
    if not table_name:
        return pd.DataFrame()
        
    query = f"SELECT * FROM {table_name}"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # 수치형 결측치 처리
    numeric_cols = ['deposit', 'monthlyRent', 'premium', 'maintenanceFee', 'size', 'floor']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
    # 지하철역 추출 및 위경도 매핑 (지도 시각화용)
    if 'nearSubwayStation' in df.columns:
        df['stationName'] = df['nearSubwayStation'].str.split(',').str[0].str.strip()
        
        # 알려진 역 위경도, 없으면 임시로 서울중심부
        def get_lat(name): return STATION_COORDS.get(name, (37.5665, 126.9780))[0]
        def get_lon(name): return STATION_COORDS.get(name, (37.5665, 126.9780))[1]
        
        df['lat'] = df['stationName'].apply(get_lat)
        df['lon'] = df['stationName'].apply(get_lon)
            
    return df

with st.spinner("데이터를 로딩 중입니다... (역 좌표 추출 포함)"):
    df = load_data()

if df.empty:
    st.error("데이터베이스에 유효한 정보가 존재하지 않습니다.")
    st.stop()

# ==========================================
# 개별 매물 상세 정보 모달 / 섹션 (상단 배치)
# 버튼 버그 수정을 위해 모달을 상단에 렌더링하고 나머지는 가림
# ==========================================
if st.session_state.selected_item_id:
    # 해당 아이템 상세 정보 가져오기
    item_df = df[df['id'] == st.session_state.selected_item_id]
    
    if not item_df.empty:
        item = item_df.iloc[0]
        st.button("⬅️ 목록으로 돌아가기", on_click=deselect_item, type="primary")
        
        st.markdown(f"## 🔎 상세 매물 정보: {item.get('title', '제목 없음')}")
        st.divider()
        
        det_c1, det_c2 = st.columns([1, 1.5])
        
        with det_c1:
            # 갤러리 이미지
            urls = []
            if 'smallPhotoUrls' in item and pd.notna(item['smallPhotoUrls']):
                try: urls = json.loads(item['smallPhotoUrls'])
                except: pass
            
            if urls:
                st.image(urls[0], use_container_width=True, caption="대표 이미지")
                # 썸네일 노출
                if len(urls) > 1:
                    thumb_cols = st.columns(min(len(urls) - 1, 5)) 
                    for idx, th_c in enumerate(thumb_cols):
                        if idx + 1 < len(urls):
                            with th_c:
                                st.image(urls[idx+1], use_container_width=True)
            else:
                st.info("첨부된 사진이 없습니다.")
                
        with det_c2:
            st.markdown("### 주요 요약 정보")
            st.markdown(f"- **업종 분류**: {item.get('businessLargeCodeName', '알수없음')} ({item.get('businessMiddleCodeName', '-')})")
            st.markdown(f"- **가격 조건**: 보증금 **{format_currency(item.get('deposit', 0))}** / 월세 **{format_currency(item.get('monthlyRent', 0))}**")
            st.markdown(f"- **부가 비용**: 권리금 **{format_currency(item.get('premium', 0))}** / 관리비 **{format_currency(item.get('maintenanceFee', 0))}**")
            st.markdown(f"- **구조 정보**: 전용면적 **{round(item.get('size', 0), 1)} ㎡** / 해당 층: **{item.get('floor', 0)} 층**")
            st.markdown(f"- **입지 조건**: {item.get('nearSubwayStation', '정보 없음')}")
            
            # --- 평가 지표 ---
            st.divider()
            st.markdown("### 📈 벤치마킹 (상대적 가치 평가)")
            biz_name = item.get('businessLargeCodeName')
            
            if pd.notna(biz_name):
                # 동일 업종 평균 비교
                biz_all_df = df[df['businessLargeCodeName'] == biz_name]
                avg_rent = biz_all_df['monthlyRent'].mean()
                avg_premium = biz_all_df['premium'].mean()
                
                curr_rent = item.get('monthlyRent', 0)
                curr_premium = item.get('premium', 0)
                
                st.write(f"**[{biz_name}] 업종 평균 대비 해당 매물 비교**")
                
                # 월세 비교 지표
                if avg_rent > 0:
                    rent_diff = ((curr_rent - avg_rent) / avg_rent) * 100
                    color = "blue" if rent_diff <= 0 else "red"
                    arrow = "⬇ (평균보다 저렴함)" if rent_diff <= 0 else "⬆ (비쌈)"
                    sym = "" if rent_diff <= 0 else "+"
                    st.markdown(f"- **월세**: 동일 업종 평균({format_currency(avg_rent)}) 대비 **<span style='color:{color}'>{sym}{rent_diff:.1f}% {arrow}</span>**", unsafe_allow_html=True)
                
                # 권리금 비교 지표
                if avg_premium > 0:
                    prem_diff = ((curr_premium - avg_premium) / avg_premium) * 100
                    p_color = "blue" if prem_diff <= 0 else "red"
                    p_arrow = "⬇ (상대적으로 낮음)" if prem_diff <= 0 else "⬆ (높음)"
                    p_sym = "" if prem_diff <= 0 else "+"
                    st.markdown(f"- **권리금**: 동일 업종 평균({format_currency(avg_premium)}) 대비 **<span style='color:{p_color}'>{p_sym}{prem_diff:.1f}% {p_arrow}</span>**", unsafe_allow_html=True)
            else:
                st.caption("비교할 수 있는 동일 업종 데이터가 부족합니다.")
                
        # 상세보기가 활성화 되어있으면 아래의 리스트/대시보드는 숨깁니다.
        st.stop()


# ==========================================
# 사이드바 (검색 및 필터링)
# ==========================================
st.sidebar.header("🔍 검색 및 필터링")

if st.sidebar.button("필터 초기화 🔄"):
    reset_filters()
    st.rerun()

search_text = st.sidebar.text_input("매물명/지역 검색", key="search_text", placeholder="예: 강남, 코너, 1층...")

st.sidebar.subheader("가격 정보 (단위: 만원)")

def get_slider_max(col):
    if df[col].empty: return 10000
    val = df[col].quantile(0.95)
    return int(val) if val > 0 else 10000

max_deposit = get_slider_max('deposit')
max_rent = get_slider_max('monthlyRent')

deposit_range = st.sidebar.slider(
    "보증금 (0 ~ 95%분위)", 
    0, max_deposit, (0, max_deposit), step=1000, key="dep_slider"
)
rent_range = st.sidebar.slider(
    "월세 (0 ~ 95%분위)", 
    0, max_rent, (0, max_rent), step=100, key="rent_slider"
)

st.sidebar.subheader("업종 정보")
if 'businessLargeCodeName' in df.columns:
    unique_businesses = df['businessLargeCodeName'].dropna().unique().tolist()
    selected_businesses = st.sidebar.multiselect(
        "대분류 업종 선택",
        options=unique_businesses,
        default=unique_businesses,
        key="biz_select"
    )
else:
    selected_businesses = []

# ==========================================
# 데이터 필터링 적용
# ==========================================
filtered_df = df.copy()

if search_text:
    filtered_df = filtered_df[
        filtered_df['title'].str.contains(search_text, case=False, na=False) |
        filtered_df['nearSubwayStation'].str.contains(search_text, case=False, na=False)
    ]

filtered_df = filtered_df[
    (filtered_df['deposit'] >= deposit_range[0]) & 
    (filtered_df['deposit'] <= deposit_range[1]) &
    (filtered_df['monthlyRent'] >= rent_range[0]) & 
    (filtered_df['monthlyRent'] <= rent_range[1])
]

if selected_businesses and 'businessLargeCodeName' in filtered_df.columns:
    filtered_df = filtered_df[filtered_df['businessLargeCodeName'].isin(selected_businesses)]

# ==========================================
# 상단 KPI 및 대시보드 메인
# ==========================================
st.title("🏪 Nemostore 상가 데이터 대시보드")
st.markdown("다양한 상가 매물을 갤러리로 탐색하고 체계적으로 분석할 수 있습니다.")

summary_count = len(filtered_df)
if summary_count == 0:
    st.info("조건에 맞는 매물이 없습니다. 좌측 패널에서 필터 조건을 완화해 보시거나 초기화 버튼을 눌러주세요.")
else:
    col1, col2, col3, col4 = st.columns(4)
    summary_avg_deposit = filtered_df['deposit'].mean()
    summary_avg_rent = filtered_df['monthlyRent'].mean()
    summary_avg_size = filtered_df['size'].mean()

    col1.metric("검색된 매물 수", f"{summary_count:,} 건")
    col2.metric("평균 보증금", format_currency(summary_avg_deposit))
    col3.metric("평균 월세", format_currency(summary_avg_rent))
    col4.metric("평균 전용면적", f"{round(summary_avg_size, 1):,} ㎡")

    st.divider()

    # ==========================================
    # 탭 구성 (갤러리, 분석, 테이블)
    # ==========================================
    tab_gallery, tab_map, tab_analytics, tab_table = st.tabs(["🖼️ 갤러리 뷰", "🗺️ 지도 위치", "📈 비교 분석", "📋 데이터 리스트"])

    # ---------- [탭 1] 매물 갤러리 ----------
    with tab_gallery:
        st.subheader("매물 갤러리 탐색")
        view_df = filtered_df.head(40) 
        
        if len(filtered_df) > 40:
            st.caption(f"검색 결과가 많아 상위 40개 매물을 우선 표시합니다. (총 {summary_count}개)")

        cols = st.columns(4)
        for i, row in view_df.reset_index(drop=True).iterrows():
            with cols[i % 4]:
                img_url = "https://via.placeholder.com/300x200?text=No+Image"
                if 'smallPhotoUrls' in row and pd.notna(row['smallPhotoUrls']):
                    try:
                        urls = json.loads(row['smallPhotoUrls'])
                        if len(urls) > 0: img_url = urls[0]
                    except:
                        pass
                
                st.image(img_url, use_container_width=True)
                title = row.get('title', '제목 없음')
                short_title = title if len(title) <= 22 else title[:22] + "..."
                st.markdown(f"**{short_title}**", help=title)
                
                st.caption(f"보증금: {format_currency(row.get('deposit', 0))} | 월세: {format_currency(row.get('monthlyRent', 0))}")
                
                # 콜백 함수 방식 사용 (상태 보존)
                st.button("상세보기🔍", key=f"btn_{row['id']}", on_click=select_item, args=(row['id'],))
                st.write("")

    # ---------- [탭 2] 지도 레이어 ----------
    with tab_map:
        st.subheader("인근 역 기반 매물 지도")
        st.caption("데이터의 지하철역 텍스트를 파싱하여 임의의 위/경도로 계산해 밀집도를 표시합니다.")
        
        if 'lat' in filtered_df.columns and 'lon' in filtered_df.columns:
            # 기본 Streamlit Map 렌더링
            map_data = filtered_df[['lat', 'lon']].dropna().rename(columns={'lat': 'latitude', 'lon': 'longitude'})
            
            # jittering(약간의 노이즈)을 주어 마커가 하나에 겹치는것을 방지
            import numpy as np
            map_data['latitude'] = map_data['latitude'] + np.random.normal(0, 0.001, len(map_data))
            map_data['longitude'] = map_data['longitude'] + np.random.normal(0, 0.001, len(map_data))
            
            st.map(map_data, size=50, color='#0044ff')
        else:
            st.info("지도에 표시할 위치 데이터가 생성되지 않았습니다.")


    # ---------- [탭 3] 분석 ----------
    with tab_analytics:
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.subheader("권역 분포도 (역 기준)")
            if 'stationName' in filtered_df.columns:
                station_counts = filtered_df['stationName'].value_counts().head(10).reset_index()
                station_counts.columns = ['역이름', '매물 수']
                
                fig1 = px.bar(
                    station_counts, x='역이름', y='매물 수',
                    title="주요 권역별 매물 보유량",
                    color='매물 수', color_continuous_scale="Blues"
                )
                fig1.update_layout(xaxis_tickangle=-45, title_font=dict(size=16, family="Malgun Gothic"))
                st.plotly_chart(fig1, use_container_width=True)

        with chart_col2:
            st.subheader("층별 임대료(월세) 비교")
            if 'floor' in filtered_df.columns and 'monthlyRent' in filtered_df.columns:
                floor_df = filtered_df[(filtered_df['floor'] >= -2) & (filtered_df['floor'] <= 10)]
                if not floor_df.empty:
                    fig2 = px.box(
                        floor_df, x='floor', y='monthlyRent',
                        title="층고에 따른 월세 분포 추이",
                        labels={'floor': '층수', 'monthlyRent': '월세(만원)'}
                    )
                    fig2.update_layout(title_font=dict(size=16, family="Malgun Gothic"))
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("해당 범위 내 층별 데이터가 부족합니다.")

    # ---------- [탭 4] 상세 데이터 목록 ----------
    with tab_table:
        col_mappings = {
            'title': '매물명',
            'businessLargeCodeName': '업종(대분류)',
            'businessMiddleCodeName': '업종(중분류)',
            'deposit': '보증금(만원)',
            'monthlyRent': '월세(만원)',
            'premium': '권리금(만원)',
            'maintenanceFee': '관리비(만원)',
            'size': '면적(㎡)',
            'floor': '해당층',
            'nearSubwayStation': '역세권'
        }
        
        display_df = filtered_df[[c for c in col_mappings.keys() if c in filtered_df.columns]].copy()
        display_df.rename(columns=col_mappings, inplace=True)
        
        st.subheader("전체 매물 상세리스트")
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="분석된 전체 결과 CSV 다운로드 📥",
            data=csv,
            file_name="nemostore_filtered_data.csv",
            mime="text/csv"
        )
