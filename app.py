import streamlit as st
import math

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
st.markdown("현재 재고와 생산 소요량, 협력사 납품 조건(MOQ/LOT)을 반영하여 최종 발주 수량을 계산합니다.")

# 품목 선택 드롭다운
part_type = st.selectbox(
    "관리 품목 선택", 
    ["블로워 모터 (Blower Motor)", "스틸 강판 (Steel Sheet)", "샤프트 (Shaft)", "마그넷 (Magnet)", "기타 직접 입력"]
)

# 입력 칸을 두 개의 단(Column)으로 분리
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 재고 및 소요량 정보")
    current_stock = st.number_input("현재 보유 재고", min_value=0, value=1500, step=100)
    production_plan = st.number_input("생산 소요량 (예상치)", min_value=0, value=5000, step=100)
    safety_stock = st.number_input("안전 재고", min_value=0, value=1000, step=100)

with col2:
    st.subheader("2. 협력사 납품 조건 (SQ/단가 기준)")
    moq = st.number_input("최소 발주 수량 (MOQ)", min_value=0, value=2000, step=100)
    lot_size = st.number_input("포장 및 입고 단위 (LOT Size)", min_value=1, value=50, step=10)

st.markdown("---")

# 실행 버튼
if st.button("최종 발주량 산출하기", type="primary"):
    result = calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size)
    
    if result == 0:
        st.info("✅ 현재 재고가 충분하여 발주가 필요하지 않습니다.")
    else:
        st.success(f"**{part_type}** 품목의 이번 발주 대상 수량은 **{result:,.0f}** 단위입니다.")
