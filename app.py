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

# 지능형 텍스트 파서 (헤더 유무 상관없이 품목코드와 수량을 자동 추출)
def extract_code_and_qty(raw_text):
    if not raw_text or not raw_text.strip():
        return {}
    
    result = {}
    lines = raw_text.strip().split("\n")
    
    for line in lines:
        # '합계', '소계' 등의 요약 라인은 건너뜀
        if any(w in line for w in ["합계", "소계", "TOTAL", "Total"]):
            continue
        
        tokens = [t.strip() for t in re.split(r"[\t, ]+", line) if t.strip()]
        if not tokens:
            continue
        
        # 1. 품목코드 탐색 (알파벳+숫자 조합 6자리 이상 또는 E/T/H/S로 시작하는 코드)
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
        
        # 2. 수량 탐색 (품목코드 이후에 나오는 숫자 중 EA 다음 숫자 또는 가장 유력한 정수값)
        found_qty = 0
        
        # 만약 'EA' 단위 키워드가 있으면 그 바로 뒷 토큰 탐색
        ea_indices = [i for i, t in enumerate(tokens) if t.upper() == "EA"]
        if ea_indices:
            target_i = ea_indices[0] + 1
            if target_i < len(tokens):
                raw_num = tokens[target_i].replace(",", "")
                try:
                    found_qty = int(float(raw_num))
                except Exception:
                    pass
        
        # 'EA'가 없거나 수량 파싱 실패 시, 품목코드 뒤에 나오는 정수/실수 중 적절한 값 채택
        if found_qty == 0:
            candidates = []
            for t in tokens[code_idx+1:]:
                clean_t = t.replace(",", "")
                try:
                    val = float(clean_t)
                    # 단가처럼 소수점이 있거나 너무 큰 금액 제외, 일반 수량 범위 필터
                    candidates.append(int(val))
                except Exception:
                    pass
            if candidates:
                # 마지막 또는 첫 번째 수량 후보
                found_qty = candidates[0]
                
        result[found_code] = found_qty
        
    return result

st.set_page_config(page_title="협력사별 발주량(P/O) 산출 시스템", layout="wide")
st.title("🏭 협력사별 n+1월 일괄 발주량(P/O) 산출 시스템")

# --- 사이드바: 마스터 등록/관리 ---
st.sidebar.header("⚙️ 협력사 품목 마스터")

# 기본 샘플 세팅 버튼 (비어있을 경우 원클릭 생성)
if st.sidebar.button("🔄 [60015 시노마그] 및 샘플 마스터 초기 세팅"):
    st.session_state.vendor_master["60015 시노마그"] = {
        "THS0168300": {"part_name": "TB7S STATOR CORE", "country": "중국", "safety_days": 14, "plt_pack_qty": 2350, "moq": 2300},
        "THS0205802": {"part_name": "CE1 eCOMP MAGNET", "country": "중국", "safety_days": 14, "plt_pack_qty": 1000, "moq": 1000},
        "THS0206803": {"part_name": "CE1 eCOMP BUSBAR ASSY", "country": "중국", "safety_days": 14, "plt_pack_qty": 500, "moq": 500},
    }
    save_master_db(st.session_state.vendor_master)
    st.sidebar.success("60015 시노마그 품목 등록 완료!")
    st.rerun()

with st.sidebar.expander("📝 협력사 및 품목 마스터 신규 추가"):
    v_input = st.text_input("업체코드/명 (예: 60015 시노마그)")
    p_code = st.text_input("품목코드 (예: THS0168300)").strip().upper()
    p_name = st.text_input("품목명 (예: TB7S STATOR CORE)")
    p_cnt = st.selectbox("조달국", ["중국", "인도", "유럽", "국내"])
    p_plt = st.number_input("PLT 포장수량(EA)", value=2350, step=50)
    p_moq = st.number_input("MOQ(EA)", value=2300, step=100)
    
    if st.button("마스터에 1건 등록/수정"):
        if v_input and p_code:
            if v_input not in st.session_state.vendor_master:
                st.session_state.vendor_master[v_input] = {}
            days = 30 if "인도" in p_cnt else (14 if "중국" in p_cnt else (90 if "유럽" in p_cnt else 14))
            st.session_state.vendor_master[v_input][p_code] = {
                "part_name": p_name,
                "country": p_cnt,
                "safety_days": days,
                "plt_pack_qty": max(1, p_plt),
                "moq": p_moq
            }
            save_master_db(st.session_state.vendor_master)
            st.success(f"[{p_code}] 등록 완료!")
            st.rerun()

st.markdown("---")

# --- 1단계: 업체 선택 ---
st.subheader("1️⃣ 발주 대상 협력사 선택")

vendor_list = list(st.session_state.vendor_master.keys())
if not vendor_list:
    st.warning("등록된 협력사가 없습니다. 좌측 사이드바의 '초기 세팅' 버튼을 먼저 눌러주세요.")
    st.stop()

selected_vendor = st.selectbox("협력사 선택", vendor_list)
vendor_items = st.session_state.vendor_master[selected_vendor]

st.info(f"선택 업체: **{selected_vendor}** | 등록된 관리 품목: **{len(vendor_items)}개 품목**")

st.markdown("---")

# --- 2단계: 재고 및 생산계획 붙여넣기 ---
st.subheader("2️⃣ 재고 현황 및 n+1월 생산계획 붙여넣기")
st.caption("사내 전산(ERP)에서 긁어서 헤더가 있든 없든 그대로 상자에 붙여넣으시면 품목코드와 수량을 알아서 찾아냅니다.")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**📦 사외창고(10OSPP01) 현재고 데이터 복사/붙여넣기**")
    stock_paste = st.text_area(
        "재고 텍스트 (Ctrl+V)", 
        placeholder="110 2026 8 10OSPP01 THS0168300 TB7S STATOR CORE ... EA 884\n...",
        height=160,
        key=f"stock_{selected_vendor}"
    )

with col2:
    st.markdown("**📅 n+1월 생산 계획 데이터 복사/붙여넣기**")
    plan_paste = st.text_area(
        "생산계획 텍스트 (Ctrl+V)", 
        placeholder="THS0168300 TB7S STATOR CORE ... EA 884563 ...\n...",
        height=160,
        key=f"plan_{selected_vendor}"
    )

# 지능형 파싱 실행
stock_map = extract_code_and_qty(stock_paste)
plan_map = extract_code_and_qty(plan_paste)

st.markdown("---")

# --- 3단계: 품목별 계산 그리드 ---
st.subheader(f"3️⃣ [{selected_vendor}] 품목별 데이터 확인 및 수정")

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
        "PLT포장단위(EA)": plt_size,
        "MOQ(EA)": moq,
    })

df_editable = pd.DataFrame(rows)

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
        "PLT포장단위(EA)": st.column_config.NumberColumn(format="%d"),
        "MOQ(EA)": st.column_config.NumberColumn(format="%d"),
    }
)

st.write("")

# --- 4단계: 일괄 산출 실행 ---
if st.button(f"🚀 [{selected_vendor}] n+1월 일괄 발주량 산출하기", type="primary", use_container_width=True):
    result_rows = []
    total_order_ea = 0
    total_order_plt = 0
    
    for _, row in edited_df.iterrows():
        c_stock = int(row["현재고(EA)"])
        p_plan = int(row["n+1월 생산소요량(EA)"])
        s_days = int(row["안전재고일수(일)"])
        plt_size = max(1, int(row["PLT포장단위(EA)"]))
        moq = int(row["MOQ(EA)"])
        
        # 일 소요량 기반 안전재고 계산
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
            "품목코드": row["품목코드"],
            "품목명": row["품목명"],
            "조달국": row["조달국"],
            "현재고(EA)": f"{c_stock:,}",
            "생산소요량(EA)": f"{p_plan:,}",
            "안전재고(EA)": f"{safe_stock:,}",
            "순수부족량(EA)": f"{max(0, pure_shortage):,}",
            "PLT포장단위": f"{plt_size:,}",
            "계산PLT": f"{exact_plt:.2f}",
            "최종 발주 PLT": f"{final_plt:,} PLT",
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
        st.metric("총 발주 수량 합계", f"{total_order_ea:,} EA")
        
    st.dataframe(df_res, use_container_width=True, hide_index=True)
    
    csv_buffer = io.StringIO()
    df_res.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    st.download_button(
        label="📥 발주 결과 엑셀(CSV) 다운로드",
        data=csv_buffer.getvalue().encode("utf-8-sig"),
        file_name=f"{selected_vendor}_발주산출결과.csv",
        mime="text/csv",
    )
