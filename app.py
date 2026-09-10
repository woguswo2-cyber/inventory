import streamlit as st
import pandas as pd
import math
import io

# 발주량 산출 함수
def calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size):
    required_qty = (production_plan + safety_stock) - current_stock
    if required_qty <= 0:
        return 0
    order_qty = max(required_qty, moq)
    return math.ceil(order_qty / lot_size) * lot_size

# 파일 판독 함수 (ERP 전산 다운로드 파일 완벽 호환)
def load_data_file(file):
    content = file.read()
    
    # 1. 일반 바이너리 엑셀(.xlsx) 시도
    try:
        return pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception:
        pass

    # 2. 구형 바이너리 엑셀(.xls) 시도
    try:
        return pd.read_excel(io.BytesIO(content), engine="xlrd")
    except Exception:
        pass

    # 3. ERP 전산 특유의 HTML형식 xls 파일 시도 (가장 유력)
    try:
        tables = pd.read_html(io.BytesIO(content))
        if tables:
            return tables[0]
    except Exception:
        pass

    # 4. CSV (utf-8 / cp949) 시도
    try:
        return pd.read_csv(io.BytesIO(content), encoding="utf-8")
    except Exception:
        pass

    try:
        return pd.read_csv(io.BytesIO(content), encoding="cp949")
    except Exception:
        pass

    raise ValueError("지원하지 않는 파일 형식이거나 파일이 손상되었습니다.")

st.set_page_config(page_title="부품/자재 발주량 산출 시스템", layout="wide")
st.title("📦 부품/자재 적정 발주량 산출 시스템")

# 사이드바 파일 업로드
st.sidebar.header("📁 사내 재고/마스터 엑셀 업로드")
uploaded_file = st.sidebar.file_uploader(
    "사내 전산 다운로드 엑셀 (.xlsx, .xls, .csv)", 
    type=["xlsx", "xls", "csv"]
)

part_db = {}

if uploaded_file is not None:
    try:
        df = load_data_file(uploaded_file)
        
        # 첫 번째 행이 헤더가 아니거나 비정상일 경우 보정
        df.columns = [str(c).strip() for c in df.columns]
        
        # 컬럼 매핑 (전산마다 다른 헤더 명칭 자동 흡수)
        col_map = {}
        for c in df.columns:
            clean_c = c.replace(" ", "")
            if "품번" in clean_c or "자재코드" in clean_c or "품목코드" in clean_c:
                col_map["품번"] = c
            elif "품명" in clean_c or "자재명" in clean_c or "품목명" in clean_c:
                col_map["품명"] = c
            elif "현재고" in clean_c or "재고" in clean_c or "수량" in clean_c:
                if "품번" not in col_map or col_map["품번"] != c:
                    col_map["현재재고"] = c
            elif "안전재고" in clean_c:
                col_map["안전재고"] = c
            elif "MOQ" in clean_c.upper() or "최소발주" in clean_c:
                col_map["MOQ"] = c
            elif "LOT" in clean_c.upper() or "포장단위" in clean_c:
                col_map["LOT"] = c

        p_col = col_map.get("품번", "품번")
        n_col = col_map.get("품명", "품명")
        s_col = col_map.get("현재재고", "현재재고")
        safe_col = col_map.get("안전재고", "안전재고")
        moq_col = col_map.get("MOQ", "MOQ")
        lot_col = col_map.get("LOT", "LOT")

        for _, row in df.iterrows():
            p_no = str(row.get(p_col, "")).strip().upper()
            if p_no and p_no != "NAN" and p_no != "NONE":
                try:
                    c_stock = int(float(str(row.get(s_col, 0)).replace(",", "")))
                except Exception:
                    c_stock = 0
                try:
                    s_stock = int(float(str(row.get(safe_col, 0)).replace(",", "")))
                except Exception:
                    s_stock = 0
                try:
                    m_qty = int(float(str(row.get(moq_col, 0)).replace(",", "")))
                except Exception:
                    m_qty = 0
                try:
                    l_size = int(float(str(row.get(lot_col, 1)).replace(",", "")))
                except Exception:
                    l_size = 1

                part_db[p_no] = {
                    "name": str(row.get(n_col, "")).strip(),
                    "current_stock": c_stock,
                    "safety_stock": s_stock,
                    "moq": m_qty,
                    "lot_size": max(1, l_size),
                }

        st.sidebar.success(f"✅ 총 {len(part_db):,}개 품목 데이터 연동 성공")
        
        # 인식된 파일의 컬럼 안내
        with st.sidebar.expander("🔍 인식된 엑셀 컬럼 확인"):
            st.write(list(df.columns))

    except Exception as e:
        st.sidebar.error(f"⚠️ 파일 로드 실패: {e}")
else:
    st.sidebar.info("💡 사내 전산 엑셀을 업로드하면 품번 입력 시 재고가 자동 입력됩니다.")

st.markdown("---")

# 1. 품목 정보 입력
st.subheader("📌 품목 정보 입력")

col_part_no, col_part_name = st.columns([1.2, 2])

with col_part_no:
    input_part_no = st.text_input(
        "품번 (Part No.) 직접 입력", 
        placeholder="예: THS0103600 입력 후 엔터"
    ).strip().upper()

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
        st.caption("🟢 전산 데이터에서 일치하는 품목을 찾았습니다.")
    else:
        part_name = st.text_input("품명 (Part Name)", value="", placeholder="품명을 직접 입력하거나 좌측에서 엑셀을 업로드하세요")
        if input_part_no:
            st.caption("🟡 엑셀에 일치하는 품번이 없거나 파일이 업로드되지 않았습니다.")

st.markdown("---")

# 2. 수량 및 발주 조건 (엑셀 값으로 자동 세팅)
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

# 3. 발주량 산출
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
