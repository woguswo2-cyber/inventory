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

# 1. XML Spreadsheet 2003 파서
def parse_xml_spreadsheet(content):
    root = ET.fromstring(content)
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    
    rows_data = []
    for row in root.iter(f"{ns}Row"):
        row_vals = []
        for cell in row.iter(f"{ns}Cell"):
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
    max_len = len(header)
    fixed_body = [r + [""] * (max_len - len(r)) if len(r) < max_len else r[:max_len] for r in body]
    return pd.DataFrame(fixed_body, columns=header)

# 2. 파일 업로드 로더
def load_data_file(file):
    content = file.read()
    try:
        df_xml = parse_xml_spreadsheet(content)
        if df_xml is not None and not df_xml.empty:
            return df_xml
    except Exception:
        pass

    try:
        return pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception:
        pass

    try:
        return pd.read_excel(io.BytesIO(content), engine="xlrd")
    except Exception:
        pass

    try:
        tables = pd.read_html(io.BytesIO(content))
        if tables:
            return tables[0]
    except Exception:
        pass

    try:
        return pd.read_csv(io.BytesIO(content), encoding="utf-8")
    except Exception:
        pass

    try:
        return pd.read_csv(io.BytesIO(content), encoding="cp949")
    except Exception:
        pass

    raise ValueError("지원하지 않는 파일 서식입니다.")

# 3. 엑셀 복사/붙여넣기(클립보드 텍스트) 파서
def parse_clipboard_text(text_data):
    if not text_data or not text_data.strip():
        return None
    try:
        return pd.read_csv(io.StringIO(text_data.strip()), sep="\t")
    except Exception:
        return pd.read_csv(io.StringIO(text_data.strip()))

st.set_page_config(page_title="부품/자재 발주량 산출 시스템", layout="wide")
st.title("📦 부품/자재 적정 발주량 산출 시스템")

# --- 사이드바 데이터 입력 영역 ---
st.sidebar.header("📁 데이터 입력 방식 선택")
input_mode = st.sidebar.radio("입력 방식", ["📋 엑셀 복사/붙여넣기 (보안망 추천)", "📂 파일 직접 업로드"], horizontal=True)

stock_db = {}
country_db = {}
df_stock = None
df_country = None

if input_mode == "📋 엑셀 복사/붙여넣기 (보안망 추천)":
    st.sidebar.markdown("---")
    st.sidebar.subheader("1. 재고 데이터 붙여넣기")
    stock_text = st.sidebar.text_area(
        "사외창고 엑셀 복사본 (헤더 포함 Ctrl+C/V)", 
        placeholder="품목코드, 품목명, 재고수량 등의 영역을 복사해서 붙여넣으세요.",
        height=140
    )
    if stock_text:
        try:
            df_stock = parse_clipboard_text(stock_text)
        except Exception as e:
            st.sidebar.error(f"재고 데이터 파싱 실패: {e}")

    st.sidebar.subheader("2. 국가 마스터 붙여넣기")
    country_text = st.sidebar.text_area(
        "국가 마스터 엑셀 복사본 (선택)", 
        placeholder="품목코드, 품목명, 조달국(국가) 영역을 복사해서 붙여넣으세요.",
        height=120
    )
    if country_text:
        try:
            df_country = parse_clipboard_text(country_text)
        except Exception as e:
            st.sidebar.error(f"국가 마스터 파싱 실패: {e}")

else:
    st.sidebar.markdown("---")
    stock_file = st.sidebar.file_uploader("1. 사외창고 재고 엑셀", type=["xlsx", "xls", "csv"])
    if stock_file:
        try:
            df_stock = load_data_file(stock_file)
        except Exception as e:
            st.sidebar.error(f"재고 파일 로드 실패: {e}")

    country_file = st.sidebar.file_uploader("2. 품목별 국가 마스터 엑셀", type=["xlsx", "xls", "csv"])
    if country_file:
        try:
            df_country = load_data_file(country_file)
        except Exception as e:
            st.sidebar.error(f"국가 마스터 로드 실패: {e}")

# 1) 재고 DataFrame 매핑
if df_stock is not None:
    df_stock.columns = [str(c).strip() for c in df_stock.columns]
    col_map = {}
    for c in df_stock.columns:
        clean_c = c.replace(" ", "")
        if clean_c in ["품목코드", "품번", "자재코드"]:
            col_map["품번"] = c
        elif clean_c in ["품목명", "품명", "자재명"]:
            col_map["품명"] = c
        elif clean_c in ["재고수량", "현재재고", "현재고", "재고"]:
            col_map["현재재고"] = c

    p_col = col_map.get("품번", "품목코드")
    n_col = col_map.get("품명", "품목명")
    s_col = col_map.get("현재재고", "재고수량")

    for _, row in df_stock.iterrows():
        p_no = str(row.get(p_col, "")).strip().upper()
        if p_no and p_no not in ["NAN", "NONE", ""]:
            raw_stock = str(row.get(s_col, 0)).replace(",", "").strip()
            try:
                c_stock = int(float(raw_stock))
            except Exception:
                c_stock = 0

            stock_db[p_no] = {
                "name": str(row.get(n_col, "")).strip(),
                "current_stock": c_stock
            }
    st.sidebar.success(f"✅ 재고 데이터: {len(stock_db):,}개 품목 연동 완료")

# 2) 국가 마스터 DataFrame 매핑 ('조달국' 완벽 지원)
if df_country is not None:
    df_country.columns = [str(c).strip() for c in df_country.columns]
    c_map = {}
    for c in df_country.columns:
        clean_c = c.replace(" ", "")
        if clean_c in ["품목코드", "품번", "자재코드"]:
            c_map["품번"] = c
        elif clean_c in ["조달국", "조달국가", "국가", "원산지", "나라"]:
            c_map["국가"] = c
        elif "일수" in clean_c or "안전재고" in clean_c:
            c_map["안전재고일수"] = c
        elif "MOQ" in clean_c.upper() or "최소발주" in clean_c:
            c_map["MOQ"] = c
        elif "LOT" in clean_c.upper() or "포장단위" in clean_c:
            c_map["LOT"] = c

    cp_col = c_map.get("품번", "품목코드")
    cnt_col = c_map.get("국가", "조달국")
    days_col = c_map.get("안전재고일수", "안전재고일수")
    moq_col = c_map.get("MOQ", "MOQ")
    lot_col = c_map.get("LOT", "LOT")

    for _, row in df_country.iterrows():
        p_no = str(row.get(cp_col, "")).strip().upper()
        if p_no and p_no not in ["NAN", "NONE", ""]:
            country_val = str(row.get(cnt_col, "")).strip()
            
            days = 0
            try:
                days = int(float(str(row.get(days_col, 0)).replace(",", "")))
            except Exception:
                pass
            
            # 마스터 국가명 기준 일수 계산
            if days == 0:
                if "인도" in country_val:
                    days = 30
                elif "중국" in country_val:
                    days = 14
                elif "유럽" in country_val or "EU" in country_val.upper():
                    days = 90

            try:
                m_qty = int(float(str(row.get(moq_col, 0)).replace(",", "")))
            except Exception:
                m_qty = 0
            try:
                l_size = int(float(str(row.get(lot_col, 1)).replace(",", "")))
            except Exception:
                l_size = 1

            country_db[p_no] = {
                "country": country_val,
                "safety_days": days,
                "moq": m_qty,
                "lot_size": max(1, l_size)
            }
    st.sidebar.success(f"✅ 국가 마스터: {len(country_db):,}개 품목 연동 완료")

st.markdown("---")

# --- 1구역: 품목 정보 조회 ---
st.subheader("📌 품목 정보 조회")

col_part_no, col_part_name = st.columns([1.2, 2])

with col_part_no:
    input_part_no = st.text_input(
        "품번 (품목코드) 직접 입력", 
        placeholder="예: E0056748C01 입력 후 엔터"
    ).strip().upper()

# 데이터 조회
stock_info = stock_db.get(input_part_no, {})
country_info = country_db.get(input_part_no, {})

default_name = stock_info.get("name", "")
default_stock = stock_info.get("current_stock", 0)

# [우선순위 1] 마스터에 등록된 국가 확인
detected_country = country_info.get("country", "")
detected_days = country_info.get("safety_days", 0)

# [우선순위 2] 마스터에 없을 때만 품명 키워드로 추정
if not detected_country and default_name:
    if "인도" in default_name:
        detected_country = "인도"
        detected_days = 30
    elif "중국" in default_name:
        detected_country = "중국"
        detected_days = 14
    elif "유럽" in default_name or "EU" in default_name.upper():
        detected_country = "유럽"
        detected_days = 90

country_list = ["중국 (2주 / 14일)", "인도 (1달 / 30일)", "유럽 (3달 / 90일)", "기타 / 직접 지정"]

# 드롭다운 인덱스 결정 (인도 우선 판별)
if "인도" in detected_country:
    country_default_idx = 1
    base_days = 30
elif "중국" in detected_country:
    country_default_idx = 0
    base_days = 14
elif "유럽" in detected_country or "EU" in detected_country.upper():
    country_default_idx = 2
    base_days = 90
else:
    country_default_idx = 3
    base_days = 14

if detected_days > 0:
    base_days = detected_days

default_moq = country_info.get("moq", 0)
default_lot = country_info.get("lot_size", 1)

with col_part_name:
    part_name = st.text_input("품명 (품목명)", value=default_name, disabled=True if default_name else False)
    if input_part_no:
        if stock_info and country_info:
            st.caption(f"🟢 [마스터 연동 완료] 조달국가: **{detected_country}** (기준 일수: **{base_days}일**)")
        elif stock_info:
            st.caption(f"🟡 재고 연동 완료 (국가 마스터 미등록 -> 품명 기준 추정: **{detected_country if detected_country else '미지정'}**)")
        else:
            st.caption("🔴 입력된 데이터에서 품목코드를 찾을 수 없습니다.")

st.markdown("---")

# --- 2구역: 조달 조건 및 생산 소요량 입력 ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 재고 및 생산 계획")
    current_stock = st.number_input(
        "현재 보유 재고 (10OSPP01 사외창고 전산 기준)", 
        value=default_stock, 
        step=10, 
        key=f"stock_{input_part_no}"
    )
    
    plan_type = st.radio("소요량 입력 기준", ["월간 생산 소요량 기준", "일일 소요량 기준"], horizontal=True)
    if plan_type == "월간 생산 소요량 기준":
        monthly_plan = st.number_input("월간 생산 소요량 (월 계획치)", min_value=0, value=0, step=500, key=f"month_plan_{input_part_no}")
        daily_usage = monthly_plan / 30.0
        production_plan = monthly_plan
    else:
        daily_usage_input = st.number_input("일일 소요량", min_value=0.0, value=0.0, step=10.0, key=f"daily_plan_{input_part_no}")
        daily_usage = daily_usage_input
        production_plan = int(daily_usage * 30)

with col2:
    st.subheader("2. 조달 국가 및 안전재고 자동 설정")
    selected_country_option = st.selectbox(
        "조달 국가 선택 (품번 입력 시 자동 선택)", 
        country_list, 
        index=country_default_idx,
        key=f"country_box_{input_part_no}"
    )
    
    if "인도" in selected_country_option:
        calc_days = 30
    elif "중국" in selected_country_option:
        calc_days = 14
    elif "유럽" in selected_country_option:
        calc_days = 90
    else:
        calc_days = base_days
        
    safety_days = st.number_input(
        "안전재고 적용 일수 (일)", 
        min_value=0, 
        value=calc_days, 
        step=1, 
        key=f"safety_days_{input_part_no}_{selected_country_option}"
    )
    
    calc_safety_stock = int(math.ceil(daily_usage * safety_days))
    
    safety_stock = st.number_input(
        f"최종 안전 재고 수량 ({safety_days}일치 자동 계산)", 
        min_value=0, 
        value=calc_safety_stock, 
        step=50,
        key=f"safety_qty_{input_part_no}_{calc_safety_stock}"
    )

st.markdown("---")

# --- 3구역: 발주 단위 (MOQ/LOT) 및 최종 산출 ---
st.subheader("3. 협력사 납품 조건 및 발주량 산출")
moq_col, lot_col = st.columns(2)
with moq_col:
    moq = st.number_input("최소 발주 수량 (MOQ)", min_value=0, value=default_moq, step=100, key=f"moq_{input_part_no}")
with lot_col:
    lot_size = st.number_input("포장 단위 (LOT Size)", min_value=1, value=default_lot, step=10, key=f"lot_{input_part_no}")

if st.button("🚀 최종 발주량 산출하기", type="primary", use_container_width=True):
    if not input_part_no:
        st.error("⚠️ 품번을 먼저 입력해주세요.")
    else:
        result = calculate_order_quantity(current_stock, production_plan, safety_stock, moq, lot_size)
        display_name = part_name if part_name else "품명 미지정"
        
        st.markdown(f"### 📋 산출 결과: `[{input_part_no}] {display_name}`")
        
        res1, res2, res3, res4 = st.columns(4)
        pure_shortage = (production_plan + safety_stock) - current_stock
        
        with res1:
            st.metric(label="설정 안전재고", value=f"{safety_stock:,} 개", help=f"{safety_days}일치 기준")
        with res2:
            st.metric(label="순수 부족 수량", value=f"{max(0, pure_shortage):,} 개")
        with res3:
            st.metric(label="적용 MOQ / LOT", value=f"{moq:,} / {lot_size:,}")
        with res4:
            st.metric(label="최종 발주 권고 수량", value=f"{result:,} 개")
            
        if result == 0:
            st.info("💡 현재고가 충분하여 신규 발주가 필요하지 않습니다.")
        elif result > pure_shortage:
            st.warning(f"⚠️ MOQ/LOT 단위 올림으로 인해 순수 부족분 대비 **{result - pure_shortage:,.0f}개** 추가 발주됩니다.")
