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

# 줄바꿈 깨짐 완벽 대응 ERP 단가 파서
def parse_erp_vendor_paste_robust(text_data, forced_vendor="", default_country="중국", default_plt=1000, default_moq=0):
    if not text_data or not text_data.strip():
        return 0
        
    days = 30 if "인도" in default_country else (14 if "중국" in default_country else (90 if ("유럽" in default_country or "EU" in default_country.upper()) else 14))
    
    # 1. 탭, 개행, 다중 공백을 모두 단일 공백으로 치환 후 토큰화
    raw_clean = text_data.replace("\r", " ")
    tokens = [t.strip() for t in re.split(r"[\t\n\s]+", raw_clean) if t.strip()]
    
    # 품번 패턴 (영문 1~3자 + 숫자/영문 혼합 6자리 이상: H0084301C01, EHA0007100, E0056748C01, THS0107800 등)
    part_pattern = re.compile(r"^[A-Z]{1,4}[0-9]{4,}[A-Z0-9]*$")
    # 협력사 코드 패턴 (5자리 내외 숫자)
    vendor_code_pattern = re.compile(r"^\d{4,6}$")
    
    found_items = []
    
    for i, token in enumerate(tokens):
        tok_upper = token.upper()
        # 회사/사업장 코드(00100, 110 등) 및 일반 단어 제외
        if tok_upper in ["00100", "110", "100", "200", "A02", "IN42", "COMMUTATOR", "MAGNET"]:
            continue
            
        if part_pattern.match(tok_upper) and len(tok_upper) >= 7:
            # 품번 발견
            p_code = tok_upper
            
            # 1) 품명 수집 (품번 바로 뒤에 나오는 영문/숫자/특수문자 단어들, 다음 품번이나 업체코드가 나오기 전까지)
            p_name_parts = []
            for next_tok in tokens[i+1:]:
                # 단가나 날짜 형태(2026-04-01, 239.5900 등)를 만나면 품명 종료
                if re.match(r"^\d{4}-\d{2}-\d{2}$", next_tok) or re.match(r"^\d+\.\d+$", next_tok):
                    break
                if vendor_code_pattern.match(next_tok) or (part_pattern.match(next_tok.upper()) and len(next_tok) >= 7):
                    break
                if next_tok in ["00100", "110", "IN42", "EA", "P", "S", "A02"]:
                    continue
                p_name_parts.append(next_tok)
                if len(p_name_parts) >= 5: # 품명이 너무 길어지는 것 방지
                    break
            p_name = " ".join(p_name_parts).strip()
            
            # 2) 협력사명/코드 탐색 (품번 앞쪽 1~5개 토큰 역추적)
            v_code = ""
            v_name_parts = []
            lookback = tokens[max(0, i-6):i]
            
            for prev_tok in reversed(lookback):
                if prev_tok in ["00100", "110", "EA", "P", "S"]:
                    continue
                if vendor_code_pattern.match(prev_tok) and not v_code:
                    v_code = prev_tok
                elif not vendor_code_pattern.match(prev_tok) and not part_pattern.match(prev_tok.upper()):
                    v_name_parts.insert(0, prev_tok)
                    
            v_name = " ".join(v_name_parts).strip()
            
            # 최종 협력사 키 지정
            if forced_vendor.strip():
                final_v = forced_vendor.strip()
            elif v_code and v_name:
                final_v = f"{v_code} {v_name}"
            elif v_code:
                final_v = v_code
            elif v_name:
                final_v = v_name
            else:
                final_v = "기타 협력사"
                
            found_items.append((final_v, p_code, p_name))

    if not found_items:
        return 0

    added_count = 0
    for v_key, p_no, p_nm in found_items:
        if v_key not in st.session_state.vendor_master:
            st.session_state.vendor_master[v_key] = {}
            
        existing = st.session_state.vendor_master[v_key].get(p_no, {})
        st.session_state.vendor_master[v_key][p_no] = {
            "part_name": p_nm if p_nm else existing.get("part_name", ""),
            "country": existing.get("country", default_country),
            "safety_days": existing.get("safety_days", days),
            "plt_pack_qty": existing.get("plt_pack_qty", default_plt),
            "moq": existing.get("moq", default_moq)
        }
        added_count += 1

    save_master_db(st.session_state.vendor_master)
    return added_count

# 전산 재고/생산계획 파서
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
            if re.match(r"^[A-Z]{1,4}[0-9]{4,}[A-Z0-9]*$", clean_tok) and len(clean_tok) >= 7:
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

# --- 사이드바 ---
st.sidebar.header("📋 협력사 마스터 관리")

with st.sidebar.expander("📥 ERP 단가등록 화면 붙여넣기 (신규 등록)", expanded=True):
    # 업체명 직접 지정 옵션 (오인식 방지용)
    manual_v_name = st.text_input("업체명 직접 지정 (선택)", placeholder="예: 62595 GREAT WALL (비워두면 자동 인식)")
    
    erp_paste_text = st.text_area(
        "ERP 표 복사본 (Ctrl+V)",
        placeholder="ERP 화면에서 복사한 데이터를 그대로 붙여넣으세요.",
        height=140
    )
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        reg_country = st.selectbox("기본 조달국", ["중국", "인도", "유럽", "국내"], index=0)
    with col_c2:
        reg_plt = st.number_input("기본 PLT당 수량", value=1000, step=100)
        
    if st.button("💾 위 ERP 데이터로 마스터 등록/추가", type="primary", use_container_width=True):
        cnt = parse_erp_vendor_paste_robust(
            erp_paste_text, 
            forced_vendor=manual_v_name, 
            default_country=reg_country, 
            default_plt=reg_plt
        )
        if cnt > 0:
            st.sidebar.success(f"총 {cnt}개 품목 등록 성공!")
            st.rerun()
        else:
            st.sidebar.error("품목을 인식하지 못했습니다. ERP 표를 다시 확인해 주세요.")

with st.sidebar.expander("✏️ 등록된 마스터 데이터 조회 및 직접 수정", expanded=True):
    master_vendors = list(st.session_state.vendor_master.keys())
    if master_vendors:
        edit_v = st.selectbox("수정할 협력사 선택", master_vendors, key="edit_vendor_sel")
        v_items = st.session_state.vendor_master.get(edit_v, {})
        
        m_rows = []
        for p_code, p_val in v_items.items():
            m_rows.append({
                "품목코드": p_code,
                "품목명": p_val.get("part_name", ""),
                "조달국": p_val.get("country", "중국"),
                "안전일수": p_val.get("safety_days", 14),
                "PLT수량": p_val.get("plt_pack_qty", 1000),
                "MOQ": p_val.get("moq", 0)
            })
        df_m_edit = pd.DataFrame(m_rows)
        
        st.caption("👇 표 안의 숫자를 더블클릭해서 수정한 뒤 아래 저장 버튼을 누르세요.")
        edited_m_df = st.data_editor(
            df_m_edit,
            use_container_width=True,
            hide_index=True,
            column_config={
                "품목코드": st.column_config.TextColumn(disabled=True),
                "품목명": st.column_config.TextColumn(),
                "조달국": st.column_config.SelectboxColumn(options=["중국", "인도", "유럽", "국내"]),
                "안전일수": st.column_config.NumberColumn(format="%d"),
                "PLT수량": st.column_config.NumberColumn(format="%d"),
                "MOQ": st.column_config.NumberColumn(format="%d"),
            }
        )
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 변경사항 영구 저장", type="primary", use_container_width=True):
                new_dict = {}
                for _, r in edited_m_df.iterrows():
                    new_dict[r["품목코드"]] = {
                        "part_name": r["품목명"],
                        "country": r["조달국"],
                        "safety_days": int(r["안전일수"]),
                        "plt_pack_qty": max(1, int(r["PLT수량"])),
                        "moq": int(r["MOQ"])
                    }
                st.session_state.vendor_master[edit_v] = new_dict
                save_master_db(st.session_state.vendor_master)
                st.success(f"[{edit_v}] 마스터가 수정되어 영구 저장되었습니다!")
                st.rerun()
                
        with col_btn2:
            if st.button("🗑️ 이 업체 삭제", use_container_width=True):
                del st.session_state.vendor_master[edit_v]
                save_master_db(st.session_state.vendor_master)
                st.warning(f"[{edit_v}] 데이터가 삭제되었습니다.")
                st.rerun()
    else:
        st.caption("등록된 협력사가 없습니다.")

with st.sidebar.expander("⚙️ 전체 데이터 초기화"):
    if st.button("⚠️ 모든 협력사 마스터 삭제 (완전 초기화)"):
        st.session_state.vendor_master = {}
        save_master_db({})
        st.rerun()

st.markdown("---")

# --- 메인 화면 1단계: 업체 선택 ---
st.subheader("1️⃣ 발주 대상 협력사 선택")

vendor_list = list(st.session_state.vendor_master.keys())
if not vendor_list:
    st.info("👈 좌측 사이드바에서 ERP 화면 데이터를 붙여넣어 협력사를 등록해 주세요.")
    st.stop()

selected_vendor = st.selectbox("발주할 협력사 선택", vendor_list)
vendor_items = st.session_state.vendor_master[selected_vendor]

st.info(f"선택 협력사: **{selected_vendor}** | 등록된 관리 품목: **총 {len(vendor_items)}개 품목**")

st.markdown("---")

# --- 메인 화면 2단계: 재고 및 생산계획 붙여넣기 ---
st.subheader("2️⃣ 재고 현황 및 n+1월 생산계획 붙여넣기")
col1, col2 = st.columns(2)
with col1:
    st.markdown("**📦 사외창고(10OSPP01) 현재고 데이터 복사/붙여넣기**")
    stock_paste = st.text_area(
        "재고 텍스트 (Ctrl+V)", 
        placeholder="전산 재고조회 화면을 복사해서 붙여넣으세요.",
        height=140,
        key=f"stock_{selected_vendor}"
    )

with col2:
    st.markdown("**📅 n+1월 생산 계획 데이터 복사/붙여넣기**")
    plan_paste = st.text_area(
        "생산계획 텍스트 (Ctrl+V)", 
        placeholder="생산계획 화면 또는 엑셀을 복사해서 붙여넣으세요.",
        height=140,
        key=f"plan_{selected_vendor}"
    )

stock_map = extract_code_and_qty(stock_paste)
plan_map = extract_code_and_qty(plan_paste)

st.markdown("---")

# --- 메인 화면 3단계: 품목별 계산 그리드 ---
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

st.caption("💡 각 품목의 [현재고], [생산소요량], [PLT당 포장수량]은 표 안에서 더블클릭하여 바로 수정 가능합니다.")
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

# --- 메인 화면 4단계: 일괄 산출 ---
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
        
        # 안전재고 = (월 소요량 / 30) * 안전일수
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
