import streamlit as st
import pandas as pd
import math

# 발주량 산출 함수
def calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size):
    required_qty = (production_plan + safety_stock) - current_stock
    if required_qty <= 0:
        return 0
    order_qty = max(required_qty, moq)
    return math.ceil(order_qty / lot_size) * lot_size

st.set_page_config(page_title="부품/자재 발주량 산출 시스템", layout="wide")
st.title("📦 부품/자재 적정 발주량 산출 시스템")

# --- 사이드바: 엑셀 파일 업로드 영역 ---
st.sidebar.header("📁 사내 재고/마스터 엑셀 업로드")
uploaded_file = st.sidebar.file_uploader(
    "사내 전산 다운로드 엑셀 (.xlsx, .xls, .csv)", 
    type=["xlsx", "xls", "csv"]
)

part_db = {}

if uploaded_file is not None:
    try:
        # 파일 형식에 맞춰 읽기
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        # 열 이름 공백 제거
        df.columns = df.columns.str.strip()

        # 엑셀 데이터를 딕셔너리로 변환 (품번을 Key로 매핑)
        for _, row in df.iterrows():
            p_no = str(row.get("품번", "")).strip().upper()
            if p_no and p_no != "NAN":
                part_db[p_no] = {
                    "name": str(row.get("품명", "")).strip(),
                    "current_stock": int(row.get("현재재고", 0)) if pd.notna(row.get("현재재고")) else 0,
                    "safety_stock": int(row.get("안전재고", 0)) if pd.notna(row.get("안전재고")) else 0,
                    "moq": int(row.get("MOQ", 0)) if pd.notna(row.get("MOQ")) else 0,
                    "lot_size": int(row.get("LOT", 1)) if pd.notna(row.get("LOT")) else 1,
                }
        st.sidebar.success(f"✅ 총 {len(part_db):,}개 품목 로드 완료")
    except Exception as e:
        st.sidebar.error(f"⚠️ 파일 로드 실패: {e}")
else:
    st.sidebar.info("💡 사내 전산에서 받은 엑셀을 업로드하면 품번 검색 시 자동 연동됩니다.")

st.markdown("---")

# --- 1구역: 품번 입력 및 데이터 매칭 ---
st.subheader("📌 품목 정보 입력")

col_part_no, col_part_name = st.columns([1.2, 2])

with col_part_no:
    input_part_no = st.text_input(
        "품번 (Part No.) 직접 입력", 
        placeholder="예: THS0103600 입력 후 엔터"
    ).strip().upper()

# 데이터 매칭 확인
is_matched = input_part_no in part_db

if is_matched:
    item = part_db[input_part_no]
    default_name = item["name"]
    default_stock = item["current_stock"]
    default_safety = item["safety_stock"]
    default_moq = item["moq"]
    default_lot = item["lot_size"]
else:
    default_name = ""
    default_stock = 0
    default_safety = 0
    default_moq = 0
    default_lot = 1

with col_part_name:
    if is_matched:
        part_name = st.text_input("품명 (Part Name)", value=default_name, disabled=True)
        st.caption("🟢 엑셀 마스터에서 일치하는 품목 정보를 찾았습니다.")
    else:
        part_name = st.text_input("품명 (Part Name)", value="", placeholder="품명을 직접 입력하거나 좌측에서 엑셀을 업로드하세요")
        if input_part_no:
            st.caption("🟡 엑셀에 없는 품번이거나 엑셀이 업로드되지 않았습니다.")

st.markdown("---")

# --- 2구역: 수량 및 발주 조건 (엑셀 값으로 자동 세팅) ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 재고 및 생산 계획")
    current_stock = st.number_input(
        "현재 보유 재고 (전산 기준)", 
        min_value=0, 
        value=default_stock, 
        step=10, 
        key=f"stock_{input_part_no}"
    )
    production_plan = st.number_input("생산 소요량 (계획치)", min_value=0, value=0, step=100)
    safety_stock = st.number_input(
        "기준 안전 재고", 
        min_value=0, 
        value=default_safety, 
        step=10, 
        key=f"safety_{input_part_no}"
    )

with col2:
    st.subheader("2. 협력사 납품 조건")
    moq = st.number_input(
        "최소 발주 수량 (MOQ)", 
        min_value=0, 
        value=default_moq, 
        step=10, 
        key=f"moq_{input_part_no}"
    )
    lot_size = st.number_input(
        "포장 단위 (LOT Size)", 
        min_value=1, 
        value=max(1, default_lot), 
        step=10, 
        key=f"lot_{input_part_no}"
    )

st.markdown("---")

# --- 3구역: 발주량 산출 ---
if st.button("🚀 최종 발주량 산출하기", type="primary", use_container_width=True):
    if not input_part_no:
        st.error("⚠️ 품번을 먼저 입력해주세요.")
    else:
        result = calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size)
        display_name = part_name if part_name else "품명 미지정"
        
        st.markdown(f"### 📋 산출 결과: `[{input_part_no}] {display_name}`")
        
        res1, res2, res3 = st.columns(3)
        pure_shortage = (production_plan + safety_stock) - current_stock
        
        with res1:
            st.metric(label="순수 부족 수량", value=f"{max(0, pure_shortage):,} 개")
        with res2:
            st.metric(label="적용 MOQ / LOT", value=f"{moq:,} / {lot_size:,}")
        with res3:
            st.metric(label="최종 발주 권고 수량", value=f"{result:,} 개")
            
        if result == 0:
            st.info("💡 보유 재고로 충당 가능하여 신규 발주가 불필요합니다.")
        elif result > pure_shortage:
            st.warning(f"⚠️ MOQ/LOT 단위 올림으로 인해 부족분 대비 **{result - pure_shortage:,.0f}개** 추가 발주됩니다.")
