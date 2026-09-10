import streamlit as st
import pandas as pd
import math
import io
import xml.etree.ElementTree as ET

# 발주량 산출 함수
def calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size):
    required_qty = (production_plan + safety_stock) - current_stock
    if required_qty <= 0:
        return 0
    order_qty = max(required_qty, moq)
    return math.ceil(order_qty / lot_size) * lot_size

# XML Spreadsheet 2003 전용 파서
def parse_xml_spreadsheet(content):
    root = ET.fromstring(content)
    # XML 네임스페이스 추출
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    
    rows_data = []
    for row in root.iter(f"{ns}Row"):
        row_vals = []
        for cell in row.iter(f"{ns}Cell"):
            # 이전 열 건너뜀(Index 속성) 대응
            idx = cell.attrib.get(f"{ns}Index")
            if idx:
                target_idx = int(idx) - 1
                while len(row_vals) < target_idx:
                    row_vals.append("")
            
            data_elem = cell.find(f"{ns}Data")
            row_vals.append(data_elem.text if data_elem is not None and data_elem.text else "")
        if any(v != "" for v in row_vals):
            rows_data.append(row_vals)
            
    if not rows_data:
        return None
        
    header = [str(col).strip() for col in rows_data[0]]
    body = rows_data[1:]
    
    # 열 길이 일치화
    max_len = len(header)
    fixed_body = [r + [""] * (max_len - len(r)) if len(r) < max_len else r[:max_len] for r in body]
    
    return pd.DataFrame(fixed_body, columns=header)

# 다기능 파일 로더
def load_data_file(file):
    content = file.read()
    
    # 1. XML 기반 ERP 엑셀 (.xls) 파싱
    try:
        df_xml = parse_xml_spreadsheet(content)
        if df_xml is not None and not df_xml.empty:
            return df_xml
    except Exception:
        pass

    # 2. 신형 엑셀 (.xlsx)
    try:
        return pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception:
        pass

    # 3. 구형 바이너리 (.xls)
    try:
        return pd.read_excel(io.BytesIO(content), engine="xlrd")
    except Exception:
        pass

    # 4. HTML 형식 (.xls)
    try:
        tables = pd.read_html(io.BytesIO(content))
        if tables:
            return tables[0]
    except Exception:
        pass

    # 5. CSV (utf-8 / cp949)
    try:
        return pd.read_csv(io.BytesIO(content), encoding="utf-8")
    except Exception:
        pass

    try:
        return pd.read_csv(io.BytesIO(content), encoding="cp949")
    except Exception:
        pass

    raise ValueError("지원하지 않는 파일 서식입니다.")

st.set_page_config(page_title="부품/자재 발주량 산출 시스템", layout="wide")
st.title("📦 부품/자재 적정 발주량 산출 시스템")

# 사이드바
st.sidebar.header("📁 사내 재고/마스터 엑셀 업로드")
uploaded_file = st.sidebar.file_uploader(
    "사내 전산 다운로드 엑셀 (.xlsx, .xls, .csv)", 
    type=["xlsx", "xls", "csv"]
)

part_db = {}

if uploaded_file is not None:
    try:
        df = load_data_file(uploaded_file)
        
        # 첫 행 컬럼 정리
        df.columns = [str(c).strip() for c in df.columns]
        
        # ERP 실제 컬럼명 자동 매핑 (품목코드, 품목명, 재고수량 등)
        col_map = {}
        for c in df.columns:
            clean_c = c.replace(" ", "")
            if clean_c in ["품목코드", "품번", "자재코드"]:
                col_map["품번"] = c
            elif clean_c in ["품목명", "품명", "자재명"]:
                col_map["품명"] = c
            elif clean_c in ["재고수량", "현재재고", "현재고", "재고"]:
                col_map["현재재고"] = c
            elif "안전재고" in clean_c:
                col_map["안전재고"] = c
            elif "MOQ" in clean_c.upper() or "최소발주" in clean_c:
                col_map["MOQ"] = c
            elif "LOT" in clean_c.upper() or "포장단위" in clean_c:
                col_map["LOT"] = c

        p_col = col_map.get("품번", "품목코드")
        n_col = col_map.get("품명", "품목명")
        s_col = col_map.get("현재재고", "재고수량")
        safe_col = col_map.get("안전재고", "안전재고")
        moq_col = col_map.get("MOQ", "MOQ")
        lot_col = col_map.get("LOT", "LOT")

        for _, row in df.iterrows():
            p_no = str(row.get(p_col, "")).strip().upper()
            if p_no and p_no not in ["NAN", "NONE", ""]:
                # 재고수량 숫자 변환
                raw_stock = str(row.get(s_col, 0)).replace(",", "").strip()
                try:
                    c_stock = int(float(raw_stock))
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
        
        with st.sidebar.expander("🔍 인식된 헤더 및 컬럼 매핑"):
            st.write("인식된 컬럼:", list(df.columns))
            st.write("매핑 정보:", col_map)

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
        "품번 (품목코드) 직접 입력", 
        placeholder="예: E0056748 또는 H0020650"
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
        part_name = st.text_input("품명 (품목명)", value=default_name, disabled=True)
        st.caption("🟢 전산 엑셀 데이터에서 일치하는 품목을 찾았습니다.")
    else:
        part_name = st.text_input("품명 (품목명)", value="", placeholder="품명을 직접 입력하거나 좌측에서 엑셀을 업로드하세요")
        if input_part_no:
            st.caption("🟡 업로드된 파일에 일치하는 품목코드가 없습니다.")

st.markdown("---")

# 2. 수량 및 발주 조건
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 재고 및 생산 계획")
    current_stock = st.number_input(
        "현재 보유 재고 (전산 재고수량 기준)", 
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
            st.info("💡 재고가 충분하여 발주가 필요하지 않습니다.")
        elif result > pure_shortage:
            st.warning(f"⚠️ MOQ/LOT 단위 올림으로 부족분 대비 **{result - pure_shortage:,.0f}개** 추가 발주됩니다.")
