import streamlit as st
import math

# 1. 품번 마스터 데이터베이스 (사내 기준 품번 매핑)
PART_MASTER = {
    "BM-1010-A": {"name": "블로워 모터", "default_moq": 2000, "default_lot": 50, "default_safety": 1000},
    # ↓ 여기에 새 품번 추가
    "NEW-9999-Z": {"name": "신규 부품명", "default_moq": 500, "default_lot": 20, "default_safety": 200},
}

# 발주량 산출 로직
def calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size):
    required_qty = (production_plan + safety_stock) - current_stock
    if required_qty <= 0:
        return 0
    order_qty = max(required_qty, moq)
    return math.ceil(order_qty / lot_size) * lot_size

st.set_page_config(page_title="부품/자재 발주량 산출 시스템", layout="wide")

st.title("📦 부품/자재 적정 발주량 산출 시스템")
st.caption("품번을 직접 입력하면 마스터에 등록된 품명과 기본 발주 조건이 자동으로 연동됩니다.")

st.markdown("---")

# --- 1구역: 품번 직접 입력 및 품명 자동 추적 ---
st.subheader("📌 품목 정보 입력")

col_part_no, col_part_name = st.columns([1.2, 2])

with col_part_no:
    input_part_no = st.text_input(
        "품번 (Part No.) 직접 입력", 
        value="", 
        placeholder="예: BM-1010-A 입력 후 엔터",
        help="등록된 예시 품번: BM-1010-A, SH-2020-B, MG-3030-C, ST-4040-D"
    ).strip().upper()  # 공백 제거 및 대문자 변환

# 입력한 품번이 마스터에 있는지 판별
is_matched = input_part_no in PART_MASTER

if is_matched:
    target_data = PART_MASTER[input_part_no]
    default_name = target_data["name"]
    default_safety = target_data["default_safety"]
    default_moq = target_data["default_moq"]
    default_lot = target_data["default_lot"]
else:
    default_name = ""
    default_safety = 0
    default_moq = 0
    default_lot = 1

with col_part_name:
    if is_matched:
        part_name = st.text_input("품명 (Part Name)", value=default_name, disabled=True)
        st.caption("🟢 등록된 품목 마스터 정보를 성공적으로 불러왔습니다.")
    else:
        part_name = st.text_input(
            "품명 (Part Name)", 
            value="", 
            placeholder= "신규 품목일 경우 품명을 직접 입력하세요" if input_part_no else "품번을 먼저 입력하세요",
            disabled=False
        )
        if input_part_no:
            st.caption("🟡 미등록 품번입니다. 품명과 발주 조건을 수기로 입력해주세요.")

st.markdown("---")

# --- 2구역: 수량 및 발주 조건 입력 ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 재고 및 생산 계획")
    current_stock = st.number_input("현재 보유 재고", min_value=0, value=1500, step=100)
    production_plan = st.number_input("생산 소요량 (계획치)", min_value=0, value=5000, step=100)
    safety_stock = st.number_input(
        "안전 재고", 
        min_value=0, 
        value=default_safety, 
        step=100,
        key=f"safety_{input_part_no}"  # 품번 바뀔 때 기본값 자동 리셋
    )

with col2:
    st.subheader("2. 발주 조건 (협력사 MOQ / LOT)")
    moq = st.number_input(
        "최소 발주 수량 (MOQ)", 
        min_value=0, 
        value=default_moq, 
        step=100,
        key=f"moq_{input_part_no}"
    )
    lot_size = st.number_input(
        "포장 단위 (LOT Size)", 
        min_value=1, 
        value=default_lot, 
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
        
        res_col1, res_col2, res_col3 = st.columns(3)
        pure_shortage = (production_plan + safety_stock) - current_stock
        
        with res_col1:
            st.metric(label="순수 부족 수량", value=f"{max(0, pure_shortage):,} 개")
        with res_col2:
            st.metric(label="적용 MOQ / LOT", value=f"{moq:,} / {lot_size:,}")
        with res_col3:
            st.metric(label="최종 발주 권고 수량", value=f"{result:,} 개")
            
        if result == 0:
            st.info("💡 현재 재고가 충분하여 발주가 필요하지 않습니다.")
        elif result > pure_shortage:
            st.warning(f"⚠️ 협력사 MOQ 또는 LOT 올림 조건으로 인해 부족분 대비 **{result - pure_shortage:,.0f}개** 추가 발주됩니다.")
