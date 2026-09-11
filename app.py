import streamlit as st
import pandas as pd
import math
import io
import json
import os
import re

MASTER_FILE = "vendor_item_master.json"

def load_master_db():
    if os.path.exists(MASTER_FILE):
        try:
            with open(MASTER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_master_db(db):
    try:
        with open(MASTER_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

if "vendor_master" not in st.session_state:
    st.session_state.vendor_master = load_master_db()

# ERP 단가등록 그리드 전용 복사/붙여넣기 파서
def parse_erp_vendor_paste(text_data, default_country="중국", default_plt=1000, default_moq=0):
    if not text_data or not text_data.strip():
        return 0
    
    lines = text_data.strip().split("\n")
    added_count = 0
    
    # 조달국 안전일수 매핑
    days = 30 if "인도" in default_country else (14 if "중국" in default_country else (90 if ("유럽" in default_country or "EU" in default_country.upper()) else 14))

    for line in lines:
        if not line.strip() or any(w in line for w in ["레코드", "회사", "사업단위", "합계"]):
            continue
        
        # 탭(\t) 또는 다중 공백으로 분리
        tokens = [t.strip() for t in line.split("\t") if t.strip()]
        if len(tokens) < 4:
            tokens = [t.strip() for t in re.split(r"\s{2,}", line) if t.strip()]
            
        # ERP 구조 매칭: 공급자번호, 공급자명, 품번, 품명 탐색
        vendor_code = ""
        vendor_name = ""
        part_no = ""
        part_name = ""
        
        for idx, tok in enumerate(tokens):
            # 품번 패턴 (알파벳으로 시작하고 7자리 이상인 코드: H0166505C01, E0056748C01, THS0168300 등)
            if re.match(r"^[A-Z][A-Z0-9]{6,}$", tok.replace("-", "").upper()):
                part_no = tok.upper()
                if idx + 1 < len(tokens):
                    part_name = tokens[idx + 1]
                # 품번 앞쪽에 공급자번호/명 위치
                if idx >= 2:
                    vendor_name = tokens[idx - 1]
                    vendor_code = tokens[idx - 2]
                elif idx == 1:
                    vendor_code = tokens[0]
                break
                
        if not part_no:
            continue
            
        # 업체 표기 통합 (예: "60015 ANHUI" 또는 "60015")
        if vendor_code and vendor_name and not vendor_code.isdigit():
            # 위치 뒤바뀜 보정
            vendor_key = f"{vendor_name} {vendor_code}".strip()
        elif vendor_code:
            vendor_key = f"{vendor_code} {vendor_name}".strip()
        else:
            vendor_key = "60015 ANHUI"
            
        if vendor_key not in st.session_state.vendor_master:
            st.session_state.vendor_master[vendor_key] = {}
            
        # 기존 저장된 데이터가 있으면 유지, 없으면 기본값 부여
        existing = st.session_state.vendor_master[vendor_key].get(part_no, {})
        st.session_state.vendor_master[vendor_key][part_no] = {
            "part_name": part_name if part_name else existing.get("part_name", ""),
            "country": existing.get("country", default_country),
            "safety_days": existing.get("safety_days", days),
            "plt_pack_qty": existing.get("plt_pack_qty", default_plt),
            "moq": existing.get("moq", default_moq)
        }
        added_count += 1
        
    save_master_db(st.session_state.vendor_master)
    return added_count

# 전산 재고 및 생산계획 텍스트 파서
def extract_code_and_qty(raw_text):
    if not raw_text or not raw_text.strip():
        return {}
    result = {}
    lines = raw_text.strip().split("\n")
    for line in lines:
        if any(w in line for w in ["합계", "소계", "TOTAL", "Total"]):
            continue
        tokens = [t.strip() for t in re.split(r"[\t, ]+", line) if t.strip()]
        if not tokens:
            continue
        
        found_code = None
        code_idx = -1
        for idx, token in enumerate(tokens):
            clean_tok = token.replace("-", "").upper()
            if re.match(r"^[A-Z][A-Z0-9]{5,}$", clean_tok):
                found_code = token.upper()
                code_idx = idx
                break
        if not found_code:
            continue
            
        found_qty = 0
        ea_indices = [i for i, t in enumerate(tokens) if t.upper() == "EA"]
        if ea_indices and ea_indices[0] + 1 < len(tokens):
            try:
                found_qty = int(float(tokens[ea_indices[0] + 1].replace(",", "")))
            except Exception:
                pass
        if found_qty == 0:
            for t in tokens[code_idx+1:]:
                try:
                    val = float(t.replace(",", ""))
                    found_qty = int(val)
                    break
                except Exception:
                    pass
        result[found_code] = found_qty
    return result

st.set_page_config(page_title="협력사별 발주량 산출 시스템", layout="wide")
st.title("🏭 협력사별 n+1월 일괄 발주량(P/O) 산출 시스템")

# --- 사이드바: ERP 화면 통째 복사/붙여넣기 마스터 등록 ---
st.sidebar.header("📋 협력사 마스터 ERP 간편 등록")
st.sidebar.caption("ERP [품목별 공급자별 단가등록] 화면의 그리드를 드래그해서 그대로 붙여넣으세요.")

with st.sidebar.expander("📥 ERP 단가등록 화면 붙여넣기 (열 편집 불필요)", expanded=True):
    erp_paste_text = st.text_area(
        "ERP 표 전체 복사본 (Ctrl+C / Ctrl+V)",
        placeholder="00100 110 60015 ANHUI H0166505C01 50TQ MAGNET ...\n00100 110 60015 ANHUI H0166537C00 T50 MAGNET ...",
        height=180
    )
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        reg_country = st.selectbox("기본 조달국", ["중국", "인도", "유럽", "국내"], index=0)
    with col_c2:
        reg_plt = st.number_input("기본 PLT당 수량", value=1000, step=100)
        
    if st.sidebar.button("💾 위 ERP 데이터로 마스터 등록/추가", type="primary", use_container_width=True):
        cnt = parse_erp_vendor_paste(erp_paste_text, default_country=reg_country, default_plt=reg_plt)
        if cnt > 0:
            st.sidebar.success(f"🎉 총 {cnt}개 품목이 협력사 마스터로 완벽 연동되었습니다!")
            st.rerun()
        else:
            st.sidebar.error("데이터를 인식하지 못했습니다. ERP 표 데이터를 다시 긁어서 붙여넣어 주세요.")

# 마스터 초기화 버튼 (필요시)
with st.sidebar.expander("⚙️ 마스터 관리 / 초기화"):
    st.write(f"현재 등록된 협력사: **{len(st.session_state.vendor_master)}개**")
    if st.button("🗑️ 마스터 전체 초기화"):
        st.session_state.vendor_master = {}
        save_master_db({})
        st.rerun()

st.markdown("---")

# --- 1단계: 업체 선택 ---
st.subheader("1️⃣ 발주 대상 협력사 선택")

vendor_list = list(st.session_state.vendor_master.keys())
if not vendor_list:
    st.info("👈 좌측 사이드바에 올려주신 ERP 캡처본 데이터를 드래그 복사해서 붙여넣고 [마스터 등록] 버튼을 눌러주세요.")
    st.stop()

selected_vendor = st.selectbox("발주할 협력사 선택", vendor_list)
vendor_items = st.session_state.vendor_master[selected_vendor]

st.info(f"선택 협력사: **{selected_vendor}** | 등록된 관리 품목: **총 {len(vendor_items)}개 품목**")

st.markdown("---")

# --- 2단계: 재고 및 생산계획 붙여넣기 ---
st.subheader("2️⃣ 재고 현황 및 n+1월 생산계획 붙여넣기")
st.caption("사내 전산 재고와 생산계획 데이터를 아래 상자에 각각 복사/붙여넣기하세요.")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**📦 사외창고(10OSPP01) 현재고 데이터 (Ctrl+V)**")
    stock_paste = st.text_area(
        "재고 텍스트", 
        placeholder="전산 재고조회 화면을 복사해서 붙여넣으세요.",
        height=140,
        key=f"stock_{selected_vendor}"
    )

with col2:
    st.markdown("**📅 n+1월 생산 계획 데이터 (Ctrl+V)**")
    plan_paste = st.text_area(
        "생산계획 텍스트", 
        placeholder="생산계획 화면 또는 엑셀을 복사해서 붙여넣으세요.",
        height=140,
        key=f"plan_{selected_vendor}"
    )

stock_map = extract_code_and_qty(stock_paste)
plan_map = extract_code_and_qty(plan_paste)

st.markdown("---")

# --- 3단계: 품목별 계산 그리드 (PLT단위/MOQ 자유 수정 가능) ---
st.subheader(f"3️⃣ [{selected_vendor}] 품목별 발주 계산 그리드")

rows = []
for code, info in vendor_items.items():
    cur_stock = stock_map.get(code, 0)
    prod_plan = plan_map.get(code, 0)
    safe_days = info.get("safety_days", 14)
    plt_size = info.get("plt_pack_qty", 1000)
    moq = info.get("moq", 0)
    
    rows.append({
        "품목코드": code,
        "품목명": info.get("part_name", ""),
        "조달국": info.get("country", "중국"),
        "현재고(EA)": cur_stock,
        "n+1월 생산소요량(EA)": prod_plan,
        "안전재고일수(일)": safe_days,
        "PLT당 포장수량(EA)": plt_size,
        "MOQ(EA)": moq,
    })

df_editable = pd.DataFrame(rows)

st.caption("💡 각 품목의 [PLT당 포장수량]이나 [MOQ]는 표 안에서 더블클릭하여 바로 수정할 수 있습니다.")
edited_df = st.data_editor(
    df_editable,
    use_container_width=True,
    hide_index=True,
    column_config={
        "품목코드": st.column_config.TextColumn(disabled=True),
        "품목명": st.column_config.TextColumn(disabled=True),
        "조달국": st.column_config.TextColumn(disabled=True),
        "현재고(EA)": st.column_config.NumberColumn(format="%d"),
        "n+1월 생산소요량(EA)": st.column_config.NumberColumn(format="%d"),
        "안전재고일수(일)": st.column_config.NumberColumn(format="%d"),
        "PLT당 포장수량(EA)": st.column_config.NumberColumn(format="%d"),
        "MOQ(EA)": st.column_config.NumberColumn(format="%d"),
    }
)

st.write("")

# --- 4단계: 최종 발주량 산출 ---
if st.button(f"🚀 [{selected_vendor}] n+1월 일괄 발주량 산출하기", type="primary", use_container_width=True):
    result_rows = []
    total_order_ea = 0
    total_order_plt = 0
    
    for _, row in edited_df.iterrows():
        p_code = row["품목코드"]
        c_stock = int(row["현재고(EA)"])
        p_plan = int(row["n+1월 생산소요량(EA)"])
        s_days = int(row["안전재고일수(일)"])
        plt_size = max(1, int(row["PLT당 포장수량(EA)"]))
        moq = int(row["MOQ(EA)"])
        
        # 안전재고 수량 = (월소요량 / 30) * 안전일수
        daily_use = p_plan / 30.0
        safe_stock = int(math.ceil(daily_use * s_days))
        
        pure_shortage = (p_plan + safe_stock) - c_stock
        
        if pure_shortage <= 0:
            final_plt = 0
            final_ea = 0
            exact_plt = 0.0
        else:
            base_qty = max(pure_shortage, moq)
            exact_plt = base_qty / plt_size
            final_plt = math.ceil(exact_plt)
            final_ea = final_plt * plt_size
            
        total_order_ea += final_ea
        total_order_plt += final_plt
        
        result_rows.append({
            "품목코드": p_code,
            "품목명": row["품목명"],
            "현재고(EA)": f"{c_stock:,}",
            "생산소요량(EA)": f"{p_plan:,}",
            "안전재고(EA)": f"{safe_stock:,}",
            "순수부족량(EA)": f"{max(0, pure_shortage):,}",
            "PLT포장수량": f"{plt_size:,}",
            "이론PLT": f"{exact_plt:.2f}",
            "최종 권고 PLT": f"{final_plt:,} PLT",
            "최종 발주 수량(EA)": f"{final_ea:,} EA"
        })

    df_res = pd.DataFrame(result_rows)
    
    st.markdown("### 📋 최종 일괄 발주 산출 결과")
    
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("대상 품목 수", f"{len(df_res)}개 품목")
    with m2:
        st.metric("총 발주 PLT 합계", f"{total_order_plt:,} PLT")
    with m3:
        st.metric("총 발주 수량(EA) 합계", f"{total_order_ea:,} EA")
        
    st.dataframe(df_res, use_container_width=True, hide_index=True)
    
    csv_buffer = io.StringIO()
    df_res.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    st.download_button(
        label="📥 발주 결과 엑셀(CSV) 다운로드",
        data=csv_buffer.getvalue().encode("utf-8-sig"),
        file_name=f"{selected_vendor}_발주산출결과.csv",
        mime="text/csv",
    )
