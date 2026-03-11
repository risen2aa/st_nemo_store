import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import os
import ast

# 페이지 기본 설정
st.set_page_config(page_title="Nemostore 상가 대시보드 v2", layout="wide")

# CSS: 갤러리 이미지, 링크 스타일 변경
st.markdown("""
    <style>
    .gallery-img { width: 100%; height: 150px; object-fit: cover; border-radius: 8px; margin-bottom: 8px;}
    .gallery-card { border: 1px solid #ddd; padding: 10px; border-radius: 10px; background-color: #fafafa; margin-bottom: 15px;}
    .prop-title { font-weight: bold; font-size: 1.1em; color: #1f77b4; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    .prop-desc { font-size: 0.9em; color: #555; }
    </style>
""", unsafe_allow_html=True)

@st.cache_data
def load_data():
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'nemostore.db')
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM items", conn)
    conn.close()
    
    # 핵심 수치형 데이터 전처리
    numeric_cols = ['deposit', 'monthlyRent', 'premium', 'sale', 'maintenanceFee', 'size']
    for col in numeric_cols:
         if col in df.columns:
             df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
             
    # 가격/면적 단위 변환 프리셋 및 컬럼 한글화 매핑용 추가 계산 공간
    df['size_py'] = df['size'] / 3.3058
    
    # 지도매핑 위경도 (데이터에 lat, lng가 없으므로 임의근사 또는 데모좌표 적용을 위해 빈 컬럼)
    # 실제로는 지하철역 기반 로직을 추가할 수 있으나 본 예제에서는 scatter_mapbox 용 dummy or skip 처리합니다.
    # 만약 위경도가 없다면 사용자가 요구한 좌표기반맵은 한계가 있으므로, 막대/분포로 우회하거나 추후 Geocoding이 필요합니다.
    
    return df

try:
    df_raw = load_data()
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

st.title("🏢 Nemostore 상가 매물 대시보드 v2")

# --- 1) 사이드바 필터 ---
st.sidebar.header("🔍 검색 및 필터링")

# 상태 상태 유지 설정 (토글값 등)
if "unit_area" not in st.session_state: st.session_state.unit_area = "㎡"
if "unit_price" not in st.session_state: st.session_state.unit_price = "만원"

st.sidebar.subheader("단위 설정")
col_ua, col_up = st.sidebar.columns(2)
with col_ua:
    unit_area = st.radio("면적 단위", ["㎡", "평"], horizontal=True, key='unit_area')
with col_up:
    unit_price = st.radio("금액 단위", ["만원", "억/만"], horizontal=True, key='unit_price')
    
# 금액 포맷터
def format_price(p):
    if unit_price == "만원": return f"{p:,.0f} 만원"
    if p >= 10000:
        억 = int(p // 10000)
        만 = int(p % 10000)
        return f"{억}억 {만}만원" if 만 > 0 else f"{억}억원"
    return f"{p:,.0f} 만원"

# 텍스트 검색
search_text = st.sidebar.text_input("매물명 또는 지하철역 검색", "")

# 아웃라이어 제거 옵션
remove_outliers = st.sidebar.checkbox("상하위 2% 극단치 🌟 매물 제외 (일반 분포 보기)", False)

# 대/중분류 연동 모델
large_biz_codes = df_raw['businessLargeCodeName'].dropna().unique().tolist()
selected_l_biz = st.sidebar.multiselect("대분류 업종", options=large_biz_codes, default=[])

if selected_l_biz:
    mid_biz_codes = df_raw[df_raw['businessLargeCodeName'].isin(selected_l_biz)]['businessMiddleCodeName'].dropna().unique().tolist()
else:
    mid_biz_codes = df_raw['businessMiddleCodeName'].dropna().unique().tolist()
selected_m_biz = st.sidebar.multiselect("중분류 업종", options=mid_biz_codes, default=[])

# 필터링 로직
q_df = df_raw.copy()

if remove_outliers:
    # 보증금, 월세 상하위 2% 제거
    q_dep_l, q_dep_h = q_df['deposit'].quantile(0.02), q_df['deposit'].quantile(0.98)
    q_rent_l, q_rent_h = q_df['monthlyRent'].quantile(0.02), q_df['monthlyRent'].quantile(0.98)
    q_df = q_df[(q_df['deposit'] >= q_dep_l) & (q_df['deposit'] <= q_dep_h) & 
                (q_df['monthlyRent'] >= q_rent_l) & (q_df['monthlyRent'] <= q_rent_h)]

if search_text:
    q_df = q_df[
        q_df['title'].str.contains(search_text, case=False, na=False) |
        q_df['nearSubwayStation'].str.contains(search_text, case=False, na=False)
    ]

if selected_l_biz:
    q_df = q_df[q_df['businessLargeCodeName'].isin(selected_l_biz)]
if selected_m_biz:
    q_df = q_df[q_df['businessMiddleCodeName'].isin(selected_m_biz)]

# --- 2) 메인보드 및 KPI 델타 ---
st.subheader(f"총 {len(q_df)}건 검색됨")

# KPI Delta 계산 (원본 대비)
mean_dep_all = df_raw['deposit'].mean()
mean_rent_all = df_raw['monthlyRent'].mean()

if len(q_df) > 0:
    mean_dep_q = q_df['deposit'].mean()
    mean_rent_q = q_df['monthlyRent'].mean()
    delta_dep = ((mean_dep_q - mean_dep_all) / mean_dep_all) * 100 if mean_dep_all else 0
    delta_rent = ((mean_rent_q - mean_rent_all) / mean_rent_all) * 100 if mean_rent_all else 0
else:
    mean_dep_q, mean_rent_q, delta_dep, delta_rent = 0,0,0,0

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("평균 보증금", format_price(mean_dep_q), f"{delta_dep:.1f}% (전체대비)", delta_color="inverse")
with col2:
    st.metric("평균 월세", format_price(mean_rent_q), f"{delta_rent:.1f}% (전체대비)", delta_color="inverse")
with col3:
    am = q_df['size_py'].mean() if unit_area == "평" else q_df['size'].mean()
    st.metric(f"평균 면적({unit_area})", f"{am:,.1f} {unit_area}")


# --- 3) 탭 뷰 ---
tab1, tab2, tab3 = st.tabs(["🖼️ 갤러리 및 상세목록", "📊 상대적 가치 평가 및 차트", "🗺️ 지도 시각화"])

with tab1:
    # 표 컬럼명 한글화 매핑
    col_mapping = {
        'title': '매물명', 'priceTypeName': '유형', 'businessLargeCodeName': '업종(대)', 'businessMiddleCodeName': '업종(중)',
        'deposit': '보증금', 'monthlyRent': '월세', 'maintenanceFee': '관리비', 'premium': '권리금',
        'nearSubwayStation': '주요역', 'floor': '층', 'size': '면적(㎡)', 'size_py': '면적(평)'
    }
    
    st.markdown("### 📋 데이터 표 (Data Table)")
    disp_df = q_df[list(col_mapping.keys())].rename(columns=col_mapping)
    st.dataframe(disp_df, width='stretch')
    
    st.markdown("---")
    st.markdown("### ��️ 매물 갤러리 뷰 (Gallery View)")
    # Grid 형태 갤러리 배치
    cards_per_row = 4
    for i in range(0, len(q_df), cards_per_row):
        cols = st.columns(cards_per_row)
        for j, col in enumerate(cols):
            if i + j < len(q_df):
                item = q_df.iloc[i + j]
                
                # 이미지 추출
                img_url = "https://via.placeholder.com/300x150?text=No+Image"
                try:
                    s_urls = ast.literal_eval(item['smallPhotoUrls'])
                    if isinstance(s_urls, list) and len(s_urls) > 0:
                        img_url = s_urls[0]
                except:
                    pass
                
                with col:
                    st.markdown(f'''
                    <div class="gallery-card">
                        <img src="{img_url}" class="gallery-img" />
                        <div class="prop-title" title="{item['title']}">{item['title']}</div>
                        <div class="prop-desc"><b>보:</b> {format_price(item['deposit'])} <br><b>월:</b> {format_price(item['monthlyRent'])}</div>
                        <div class="prop-desc">🚉 {item['nearSubwayStation']}</div>
                    </div>
                    ''', unsafe_allow_html=True)
                    
                    with st.expander("📝 상세 보기 및 가치 평가"):
                        st.markdown(f"**업종:** {item['businessLargeCodeName']} > {item['businessMiddleCodeName']}")
                        st.markdown(f"**층:** {item['floor']}층 | **면적:** {item['size_py']:.1f}평")
                        # 동일 역세권 벤치마킹
                        same_st_avg = df_raw[df_raw['nearSubwayStation'] == item['nearSubwayStation']]['monthlyRent'].mean()
                        if pd.notna(same_st_avg) and same_st_avg > 0:
                            diff = ((item['monthlyRent'] - same_st_avg) / same_st_avg) * 100
                            arrow = "🔺 비쌈" if diff > 0 else "🔻 저렴"
                            st.info(f"동일 역세권 평균 월세({format_price(same_st_avg)}) 대비 {abs(diff):.1f}% {arrow}")

with tab2:
    st.markdown("### 📈 층별 및 업종별 벤치마킹 분석")
    col2_1, col2_2 = st.columns(2)
    with col2_1:
        # 1. 층별 Boxplot
        st.subheader("층수 그룹별 월세 프리미엄 (Boxplot)")
        def group_floor(f):
            try:
                f_int = int(f)
                if f_int < 0: return "지하"
                if f_int == 1: return "1층"
                return "2층 이상"
            except:
                return "기타"
        
        q_df['floor_group'] = q_df['floor'].apply(group_floor)
        fig_box = px.box(q_df, x="floor_group", y="monthlyRent", color="floor_group", 
                         labels={"floor_group": "층 그룹", "monthlyRent": "월세 (만원)"},
                         category_orders={"floor_group": ["지하", "1층", "2층 이상", "기타"]})
        st.plotly_chart(fig_box, width='stretch')

    with col2_2:
        st.subheader("상권(역세권)별 월세 및 보증금 분포")
        # 데이터가 너무 많아 산점도 복잡, 전용면적 대비 산점도
        fig_scat = px.scatter(q_df, x="size" if unit_area=="㎡" else "size_py", y="monthlyRent", 
                              color="floor_group", size="deposit", hover_name="title",
                              labels={"size": "전용면적(㎡)", "size_py": "전용면적(평)", "monthlyRent": "월세 (만원)"})
        st.plotly_chart(fig_scat, width='stretch')

with tab3:
    st.markdown("### 🗺️ 공간 기반 상권 밀집도 분석")
    st.warning("경고: 수집된 원본 데이터에 위도(lat), 경도(lng) 좌표 필드가 없어, 현재 화면에서는 공간 시각화 구동이 불가능합니다. 추후 Geocoding API를 통해 `nearSubwayStation` 이나 주소값을 변환한 값을 추가하시면 `st.map` 또는 `px.scatter_mapbox`를 이용해 지도 시각화가 활성화됩니다.")
    st.markdown("*(예시 구현 코드)*")
    st.code("""
# 만약 q_df에 'lat', 'lng' 컬럼이 존재한다면:
st.map(q_df[['lat', 'lng']])
    """, language="python")
