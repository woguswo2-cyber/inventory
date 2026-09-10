import streamlit as st
import math

# 1. 품번 마스터 데이터베이스 (사내 품번 및 기본 스펙 매핑)
PART_MASTER = {
    "BM-1010-A": {
        "name": "블로워 모터 (Blower Motor Sub-Assy)",
        "default_moq": 2000,
        "default_lot": 50,
        "default_safety": 1000
    },
    "SH-2020-B": {
        "name": "모터 샤프트 (Motor Shaft)",
        "default_moq": 5000,
        "default_lot": 500,
        "default_safety": 1500
    },
    "MG-3030-C": {
        "name": "영구자석 (Ferrite Magnet)",
        "default_moq": 10000,
        "default_lot": 1000,
        "default_safety": 3000
    },
    "ST-4040-D": {
        "name": "스틸 강판 (Steel Sheet Coil)",
        "default_moq": 1000,
        "default_lot": 100,
        "default_safety": 500
    }
}

# 발주량 산출 함수
def calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size):
    required_qty = (production_plan + safety_stock) - current_stock
    if required_qty <= 0:
        return 0
    order_qty = max(required_qty, moq)
    return math.ceil(order_qty / lot_size) * lot_size

# 웹 페이지 설정
st.set_page_config(page_title="부품/자재 발주량 산출 시스템", layout="wide")

st.title("📦 부품/자재 적정 발주량 산출 시스템")
st.caption("품번을 선택하면 품명과 기준 납품 조건(MOQ/LOT)이 자동 연동됩니다.")

st.markdown("---")

# --- 1구역: 품번 및 품명 연동 영역 ---
st.subheader("📌 품목 정보 조회")

col_part_no, col_part_name = st.columns([1.2, 2])

with col_part_no:
    part_options = list(PART_MASTER.keys()) + ["직접 입력 (신규 품번)"]
    selected_part_no = st.selectbox("품번 (Part No.) 선택", part_options)

with col_part_name:
    if selected_part_no in PART_MASTER:
        part_info = PART_MASTER[selected_part_no]
        # 품번 선택 시 품명을 읽기 전용 텍스트 필드로 자동 표시
        part_name = st.text_input("품명 (Part Name)", value=part_info["name"], disabled=True)
    else:
        # '직접 입력'을 골랐을 때 품번/품명 모두 수기 기입 가능
        part_info = {"default_moq": 0, "default_lot": 1, "default_safety": 0}
        custom_part_no = st.text_input("신규 품번 입력", placeholder="예: CR-5050-E")
        part_name = st.text_input("신규 품명 입력", placeholder="예: 콘덴서 / 하우징류")

st.markdown("---")

# --- 2구역: 수량 및 조건 입력 영역 ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 재고 및 생산 계획")
    current_stock = st.number_input("현재 보유 재고", min_value=0, value=1500, step=100)
    production_plan = st.number_input("생산 소요량 (계획치)", min_value=0, value=5000, step=100)
    safety_stock = st.number_input(
        "안전 재고", 
        min_value=0, 
        value=part_info["default_safety"], 
        step=100, 
        help="품번 선택 시 마스터 기준값이 기본으로 세팅됩니다."
    )

with col2:
    st.subheader("2. 발주 조건 (협력사 MOQ / LOT)")
    moq = st.number_input(
        "최소 발주 수량 (MOQ)", 
        min_value=0, 
        value=part_info["default_moq"], 
        step=100, 
        help="협력사 최소 생산 단위"
    )
    lot_size = st.number_input(
        "포장 단위 (LOT Size)", 
        min_value=1, 
        value=part_info["default_lot"], 
        step=10, 
        help="박스/파렛트 단위 (올림 기준)"
    )

st.markdown("---")

# --- 3구역: 발주량 산출 및 결과 출력 ---
if st.button("🚀 최종 발주량 산출하기", type="primary", use_container_width=True):
    result = calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size)
    display_part_no = custom_part_no if selected_part_no == "직접 입력 (신규 품번)" else selected_part_no
    
    # 결과 표시
    st.markdown(f"### 📋 산출 결과: `[{display_part_no}] {part_name}`")
    
    res_col1, res_col2, res_col3 = st.columns(3)
    with res_col1:
        pure_shortage = (production_plan + safety_stock) - current_stock
        st.metric(label="순수 부족 수량", value=f"{max(0, pure_shortage):,} 개")
    with res_col2:
        st.metric(label="적용 MOQ / LOT", value=f"{moq:,} / {lot_size:,}")
    with res_col3:
        st.metric(label="최종 발주 권고 수량", value=f"{result:,} 개")
        
    if result == 0:
        st.info("💡 현재 보유 재고로 생산 및 안전재고 충당이 가능하여 발주가 필요하지 않습니다.")
    elif result > pure_shortage:
        st.warning(f"⚠️ 협력사 MOQ/LOT 단위 올림 조건으로 인해 순수 부족분보다 **{result - pure_shortage:,.0f}개** 추가 발주됩니다.")
