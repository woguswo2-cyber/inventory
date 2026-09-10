import streamlit as st
import pandas as pd
import math
import io
import json
import os
import xml.etree.ElementTree as ET

DB_FILE = "country_master.json"

# 영구 저장용 마스터 데이터 로드/저장 함수
def load_country_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_country_db(db):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

if "country_db" not in st.session_state:
    st.session_state.country_db = load_country_db()

# 발주량 및 PLT 산출 핵심 함수
def calculate_order_logic(current_stock, production_plan, safety_stock, moq, plt_pack_qty):
    # 1. 순수 부족 수량 (EA)
    required_qty = (production_plan + safety_stock) - current_stock
    if required_qty <= 0:
        return 0, 0, 0, 0, 0
    
    # 2. MOQ 반영 수량 (EA)
    base_qty = max(required_qty, moq)
    
    # 3. PLT 포장단위 올림 계산
    if plt_pack_qty > 1:
        exact_plt = base_qty / plt_pack_qty  # 예: 63.77 PLT
        final_plt = math.ceil(exact_plt)      # 예: 64 PLT
        final_order_ea = final_plt * plt_pack_qty  # 예: 64 * 2350 = 150,400 EA
    else:
        exact_plt = base_qty
        final_plt = base_qty
        final_order_ea = base_qty
        
    return final_order_ea, final_plt, exact_plt, required_qty, base_qty

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

# 3. 엑셀 복사/붙여넣기 파서
def parse_clipboard_text(text_data):
    if not text_data or not text_data.strip():
        return None
    try:
        return pd.read_csv(io.StringIO(text_data.strip()), sep="\t")
    except Exception:
        return pd.read_csv(io.StringIO(text_data.strip()))

st.set_page_config(page_title="부품/자재 발주량 산출 시스템", layout="wide")
st.title("📦 부품/자재 적정 발주량 산출 시스템")

# --- 사이드바 ---
st.sidebar.header("📁 데이터 입력 방식")
input_mode = st.sidebar.radio("입력 방식", ["📋 엑셀 복사/붙여넣기 (보안망 추천)", "📂 파일 직접 업로드"], horizontal=True)

stock_db = {}
df_stock = None

if input_mode == "📋 엑셀 복사/붙여넣기 (보안망 추천)":
    st.sidebar.markdown("---")
    st.sidebar.subheader("재고 데이터 붙여넣기")
    stock_text = st.sidebar.text_area(
        "사외창고 엑셀 복사본 (헤더 포함 Ctrl+C/V)", 
        placeholder="품목코드, 품목명, 재고수량 등의 영역을 복사해서 붙여넣으세요.",
        height=180
    )
    if stock_text:
        try:
            df_stock = parse_clipboard_text(stock_text)
        except Exception as e:
            st.sidebar.error(f"재고 데이터 파싱 실패: {e}")
else:
    st.sidebar.markdown("---")
    stock_file = st.sidebar.file_uploader("사외창고 재고 엑셀 업로드", type=["xlsx", "xls", "csv"])
    if stock_file:
        try:
            df_stock = load_data_file(stock_file)
        except Exception as e:
            st.sidebar.error(f"재고 파일 로드 실패: {e}")

# 재고 DataFrame 매핑
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
    st.sidebar.success(f"✅ 재고 연동 완료: {len(stock_db):,}개 품목")

st.sidebar.markdown("---")
st.sidebar.subheader("🧠 기억된 품목 기준 마스터")
st.sidebar.caption(f"현재 시스템이 기억 중인 품목: **{len(st.session_state.country_db):,}개**")

with st.sidebar.expander("📥 엑셀로 기준 마스터 대량 추가/갱신"):
    bulk_country_text = st.text_area("품목코드, 조달국, PLT포장수량, MOQ 붙여넣기", height=100)
    if st.button("마스터에 일괄 추가/반영"):
        df_bulk = parse_clipboard_text(bulk_country_text)
        if df_bulk is not None:
            df_bulk.columns = [str(c).strip() for c in df_bulk.columns]
            p_key = next((c for c in df_bulk.columns if any(k in c.replace(" ","") for k in ["품목코드", "품번"])), df_bulk.columns[0])
            c_key = next((c for c in df_bulk.columns if any(k in c.replace(" ","") for k in ["조달국", "국가"])), df_bulk.columns[1])
            l_key = next((c for c in df_bulk.columns if any(k in c.upper() for k in ["PLT", "파레트", "포장단위", "LOT"])), None)
            m_key = next((c for c in df_bulk.columns if "MOQ" in c.upper()), None)
            
            for _, r in df_bulk.iterrows():
                pn = str(r.get(p_key, "")).strip().upper()
                ct = str(r.get(c_key, "")).strip()
                lot_v = int(float(str(r.get(l_key, 1)).replace(",", ""))) if l_key and pd.notna(r.get(l_key)) else 1
                moq_v = int(float(str(r.get(m_key, 0)).replace(",", ""))) if m_key and pd.notna(r.get(m_key)) else 0
                
                if pn and ct:
                    st.session_state.country_db[pn] = {
                        "country": ct,
                        "safety_days": 30 if "인도" in ct else (14 if "중국" in ct else (90 if ("유럽" in ct or "EU" in ct.upper()) else 14)),
                        "plt_pack_qty": max(1, lot_v),
                        "moq": moq_v
                    }
            save_country_db(st.session_state.country_db)
            st.success("일괄 저장 완료!")
            st.rerun()

st.markdown("---")

# --- 1구역: 품목 정보 조회 ---
st.subheader("📌 품목 정보 조회")

col_part_no, col_part_name = st.columns([1.2, 2])

with col_part_no:
    input_part_no = st.text_input(
        "품번 (품목코드) 직접 입력", 
        placeholder="예: THS0107800 입력 후 엔터"
    ).strip().upper()

stock_info = stock_db.get(input_part_no, {})
saved_info = st.session_state.country_db.get(input_part_no, {})

default_name = stock_info.get("name", "")
default_stock = stock_info.get("current_stock", 0)

detected_country = saved_info.get("country", "")
detected_days = saved_info.get("safety_days", 0)

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

with col_part_name:
    part_name = st.text_input("품명 (품목명)", value=default_name, disabled=True if default_name else False)
    if input_part_no:
        if input_part_no in st.session_state.country_db:
            st.caption(f"🧠 [시스템 기억 정보] 조달국가: **{detected_country}** (기준 일수: **{base_days}일**)")
        elif default_name:
            st.caption(f"💡 신규 품목 추정: **{detected_country if detected_country else '미지정'}** (아래에서 수정 후 저장 가능)")
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
    st.subheader("2. 조달 국가 및 안전재고 설정")
    selected_country_option = st.selectbox(
        "조달 국가 선택 (품번 입력 시 자동 세팅)", 
        country_list, 
        index=country_default_idx,
        key=f"country_box_{input_part_no}"
    )
    
    if "인도" in selected_country_option:
        calc_days = 30
        pure_cname = "인도"
    elif "중국" in selected_country_option:
        calc_days = 14
        pure_cname = "중국"
    elif "유럽" in selected_country_option:
        calc_days = 90
        pure_cname = "유럽"
    else:
        calc_days = base_days
        pure_cname = "기타"
        
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

# --- 3구역: 협력사 납품 조건 (PLT 포장단위 우선 배치) ---
st.subheader("3. 협력사 납품 조건 (포장단위 및 MOQ)")

saved_plt_pack = saved_info.get("plt_pack_qty", 2350)  # 기본 추천 2,350
saved_moq = saved_info.get("moq", 0)

lot_col, moq_col = st.columns(2)
with lot_col:
    plt_pack_qty = st.number_input(
        "⭐ 파레트(PLT)당 포장 수량 (EA / PLT)", 
        min_value=1, 
        value=max(1, saved_plt_pack), 
        step=50, 
        key=f"plt_pack_{input_part_no}",
        help="1개 파레트에 실리는 낱개 수량입니다. (예: 2,350 입력 시 2,350개 단위로 올림하여 PLT 발주량 산출)"
    )
with moq_col:
    moq = st.number_input(
        "최소 발주 수량 (MOQ)", 
        min_value=0, 
        value=saved_moq, 
        step=100, 
        key=f"moq_{input_part_no}",
        help="협력사 최소 발주 단위(EA). 없으면 0으로 두셔도 무방합니다."
    )

if input_part_no:
    if st.button("💾 이 품목의 기준 정보(조달국가/PLT포장수량/MOQ) 영구 기억하기"):
        st.session_state.country_db[input_part_no] = {
            "country": pure_cname,
            "safety_days": safety_days,
            "plt_pack_qty": plt_pack_qty,
            "moq": moq
        }
        save_country_db(st.session_state.country_db)
        st.success(f"[{input_part_no}] 기준 정보(국가: {pure_cname}, PLT포장: {plt_pack_qty:,} EA, MOQ: {moq:,} EA) 저장 완료!")
        st.rerun()

st.write("")

# --- 4구역: 최종 발주량 산출 결과 ---
if st.button("🚀 최종 발주량 산출하기", type="primary", use_container_width=True):
    if not input_part_no:
        st.error("⚠️ 품번을 먼저 입력해주세요.")
    else:
        final_order_ea, final_plt, exact_plt, pure_shortage, base_qty = calculate_order_logic(
            current_stock, production_plan, safety_stock, moq, plt_pack_qty
        )
        display_name = part_name if part_name else "품명 미지정"
        
        st.markdown(f"### 📋 산출 결과: `[{input_part_no}] {display_name}`")
        
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            st.metric(label="설정 안전재고", value=f"{safety_stock:,} EA", help=f"{safety_days}일치 기준")
        with c2:
            st.metric(label="순수 부족 수량", value=f"{max(0, pure_shortage):,} EA")
        with c3:
            st.metric(label="PLT 포장 규격", value=f"{plt_pack_qty:,} EA/PLT")
        with c4:
            # 실무 요청 완벽 반영: 최종 발주 수량은 EA이고 뱃지에 몇 PLT인지 표시
            if final_order_ea > 0:
                st.metric(
                    label="최종 권고 발주 수량", 
                    value=f"{final_order_ea:,} EA", 
                    delta=f"{final_plt:,} PLT 발주"
                )
            else:
                st.metric(label="최종 권고 발주 수량", value="0 EA", delta="발주 불필요")
            
        if final_order_ea == 0:
            st.info("💡 현재고가 충분하여 신규 발주가 필요하지 않습니다.")
        else:
            diff_ea = final_order_ea - pure_shortage
            st.success(
                f"""
                ### 🎯 발주 결정 내용
                * **순수 부족 수량**: **{pure_shortage:,} EA**
                * **파레트 환산 계산**: {pure_shortage:,} EA ÷ {plt_pack_qty:,} EA = **{exact_plt:.2f} PLT**
                * **포장 단위 올림 적용**: **{final_plt:,} PLT** (소수점 올림 처리)
                * **👉 최종 발주 수량 확정**: {final_plt:,} PLT × {plt_pack_qty:,} EA = **{final_order_ea:,} EA** (여유분: +{diff_ea:,} EA)
                """
            )
