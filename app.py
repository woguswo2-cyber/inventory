import streamlit as st
import pandas as pd
import math
import io
import json
import os

MASTER_FILE = "vendor_item_master.json"

# 마스터 데이터 로드/저장
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

# 클립보드 텍스트 파서 (Tab / Comma 대응)
def parse_clipboard_text(text_data):
    if not text_data or not text_data.strip():
        return None
    try:
        return pd.read_csv(io.StringIO(text_data.strip()), sep="\t")
    except Exception:
        try:
            return pd.read_csv(io.StringIO(text_data.strip()))
        except Exception:
            return None

st.set_page_config(page_title="협력사별 일괄 발주량(P/O) 산출 시스템", layout="wide")
st.title("🏭 협력사별 n+1월 일괄 발주량(P/O) 산출 시스템")
st.caption("업체를 선택하고 재고와 생산계획을 붙여넣으면 전 품목의 PLT 포장단위 기준 최종 발주량을 일괄 산출합니다.")

# --- 사이드바: 업체별 기준 마스터 관리 ---
st.sidebar.header("⚙️ 협력사 품목 마스터 관리")
st.sidebar.caption(f"등록된 협력사 수: **{len(st.session_state.vendor_master)}개사**")

with st.sidebar.expander("📥 업체 품목 마스터 등록/갱신 (엑셀 복사/붙여넣기)"):
    st.markdown("""
    **권장 엑셀 컬럼 헤더:**  
    `업체명`(또는 업체코드), `품목코드`, `품목명`, `조달국`, `PLT포장수량`, `MOQ`
    """)
    bulk_master_text = st.text_area("마스터 엑셀 붙여넣기 (Ctrl+V)", height=150)
    if st.button("마스터에 저장하기", type="secondary"):
        df_m = parse_clipboard_text(bulk_master_text)
        if df_m is not None:
            df_m.columns = [str(c).strip() for c in df_m.columns]
            v_col = next((c for c in df_m.columns if any(k in c.replace(" ","") for k in ["업체명", "업체코드", "협력사", "공급사"])), df_m.columns[0])
            p_col = next((c for c in df_m.columns if any(k in c.replace(" ","") for k in ["품목코드", "품번"])), df_m.columns[1])
            n_col = next((c for c in df_m.columns if any(k in c.replace(" ","") for k in ["품목명", "품명"])), None)
            c_col = next((c for c in df_m.columns if any(k in c.replace(" ","") for k in ["조달국", "국가", "원산지"])), None)
            plt_col = next((c for c in df_m.columns if any(k in c.upper() for k in ["PLT", "파레트", "포장단위"])), None)
            moq_col = next((c for c in df_m.columns if "MOQ" in c.upper()), None)
            
            count = 0
            for _, r in df_m.iterrows():
                vendor = str(r.get(v_col, "")).strip()
                pno = str(r.get(p_col, "")).strip().upper()
                if not vendor or not pno or pno in ["NAN", "NONE"]:
                    continue
                
                pname = str(r.get(n_col, "")).strip() if n_col else ""
                country = str(r.get(c_col, "중국")).strip() if c_col else "중국"
                
                # 안전재고 일수 자동 매핑
                days = 30 if "인도" in country else (14 if "중국" in country else (90 if ("유럽" in country or "EU" in country.upper()) else 14))
                
                plt_val = int(float(str(r.get(plt_col, 1000)).replace(",", ""))) if plt_col and pd.notna(r.get(plt_col)) else 1000
                moq_val = int(float(str(r.get(moq_col, 0)).replace(",", ""))) if moq_col and pd.notna(r.get(moq_col)) else 0
                
                if vendor not in st.session_state.vendor_master:
                    st.session_state.vendor_master[vendor] = {}
                
                st.session_state.vendor_master[vendor][pno] = {
                    "part_name": pname,
                    "country": country,
                    "safety_days": days,
                    "plt_pack_qty": max(1, plt_val),
                    "moq": moq_val
                }
                count += 1
            save_master_db(st.session_state.vendor_master)
            st.success(f"총 {count}개 품목 마스터 반영 완료!")
            st.rerun()

st.markdown("---")

# --- 1단계: 발주 대상 업체 선택 ---
st.subheader("1️⃣ 발주 대상 협력사 선택")

vendor_list = list(st.session_state.vendor_master.keys())
col_v1, col_v2 = st.columns([1.5, 2])

with col_v1:
    if not vendor_list:
        st.warning("⚠️ 등록된 협력사가 없습니다. 좌측 사이드바에서 마스터를 먼저 등록하거나 아래 샘플을 추가하세요.")
        if st.button("💡 테스트용 샘플 업체 데이터 생성"):
            st.session_state.vendor_master = {
                "인도T55공급사": {
                    "E0056748C01": {"part_name": "T55 EU_YP LHD END COVER ASM", "country": "인도", "safety_days": 30, "plt_pack_qty": 500, "moq": 1000},
                    "E0056750C01": {"part_name": "T55 EU_YP RHD END COVER ASM", "country": "인도", "safety_days": 30, "plt_pack_qty": 500, "moq": 1000},
                    "E0070198C08": {"part_name": "61CEPS(65A) MC S/PLATE ASM", "country": "인도", "safety_days": 30, "plt_pack_qty": 1000, "moq": 2000},
                },
                "중국모터코어사": {
                    "THS0107800": {"part_name": "TB5H STATOR CORE", "country": "중국", "safety_days": 14, "plt_pack_qty": 2350, "moq": 2300},
                    "THS0103600": {"part_name": "TB5H ROTOR CORE", "country": "중국", "safety_days": 14, "plt_pack_qty": 1800, "moq": 1800},
                }
            }
            save_master_db(st.session_state.vendor_master)
            st.rerun()
        selected_vendor = None
    else:
        selected_vendor = st.selectbox("협력사명 (또는 업체코드) 선택", vendor_list)

if selected_vendor:
    vendor_items = st.session_state.vendor_master[selected_vendor]
    with col_v2:
        st.info(f"선택 업체: **{selected_vendor}** | 등록 관리 품목: **총 {len(vendor_items)}개**")

    st.markdown("---")

    # --- 2단계: 재고 및 생산계획 붙여넣기 ---
    st.subheader("2️⃣ 재고 현황 및 n+1월 생산계획 데이터 입력")
    st.caption("사내 전산(ERP)에서 복사한 재고 데이터와 생산계획 데이터를 아래 상자에 각각 붙여넣으세요.")

    col_in1, col_in2 = st.columns(2)

    with col_in1:
        st.markdown("**📦 현재고 데이터 붙여넣기 (사외창고 10OSPP01 등)**")
        stock_paste = st.text_area(
            "재고 엑셀 복사 (품목코드, 재고수량 포함)", 
            placeholder="품목코드\t품목명\t재고수량\nE0056748C01\tT55 END COVER\t1500\n...",
            height=140,
            key=f"stock_paste_{selected_vendor}"
        )

    with col_in2:
        st.markdown("**📅 n+1월 생산 소요 계획 붙여넣기**")
        plan_paste = st.text_area(
            "생산계획 엑셀 복사 (품목코드, 계획수량 포함)", 
            placeholder="품목코드\t월간소요량\nE0056748C01\t10000\n...",
            height=140,
            key=f"plan_paste_{selected_vendor}"
        )

    # 파싱 및 매핑 딕셔너리 생성
    stock_dict = {}
    if stock_paste:
        df_sp = parse_clipboard_text(stock_paste)
        if df_sp is not None:
            df_sp.columns = [str(c).strip() for c in df_sp.columns]
            p_k = next((c for c in df_sp.columns if any(k in c.replace(" ","") for k in ["품목코드", "품번"])), df_sp.columns[0])
            s_k = next((c for c in df_sp.columns if any(k in c.replace(" ","") for k in ["재고수량", "현재재고", "현재고", "수량"])), None)
            if s_k:
                for _, r in df_sp.iterrows():
                    code = str(r.get(p_k, "")).strip().upper()
                    try:
                        qty = int(float(str(r.get(s_k, 0)).replace(",", "")))
                    except Exception:
                        qty = 0
                    if code:
                        stock_dict[code] = qty

    plan_dict = {}
    if plan_paste:
        df_pp = parse_clipboard_text(plan_paste)
        if df_pp is not None:
            df_pp.columns = [str(c).strip() for c in df_pp.columns]
            p_k = next((c for c in df_pp.columns if any(k in c.replace(" ","") for k in ["품목코드", "품번"])), df_pp.columns[0])
            pl_k = next((c for c in df_pp.columns if any(k in c.replace(" ","") for k in ["계획", "소요", "수량", "월간"])), None)
            if pl_k:
                for _, r in df_pp.iterrows():
                    code = str(r.get(p_k, "")).strip().upper()
                    try:
                        p_qty = int(float(str(r.get(pl_k, 0)).replace(",", "")))
                    except Exception:
                        p_qty = 0
                    if code:
                        plan_dict[code] = p_qty

    st.markdown("---")

    # --- 3단계: 전체 품목 그리드 확인 및 수동 조정 ---
    st.subheader(f"3️⃣ [{selected_vendor}] 전 품목 발주량 일괄 계산 테이블")
    
    rows = []
    for code, info in vendor_items.items():
        cur_stock = stock_dict.get(code, 0)
        prod_plan = plan_dict.get(code, 0)
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

    # 데이터 에디터로 표시 (화면에서 바로 수정 가능)
    st.caption("💡 붙여넣은 데이터가 자동 입력되었으며, 필요시 표 안의 숫자를 더블클릭해 직접 수정할 수 있습니다.")
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
            
            # 안전재고 EA 계산: (월간소요량 / 30) * 안전일수
            daily_use = p_plan / 30.0
            safe_stock = int(math.ceil(daily_use * s_days))
            
            # 순수 부족량
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
                "현재고": f"{c_stock:,}",
                "생산소요량": f"{p_plan:,}",
                "안전재고(EA)": f"{safe_stock:,}",
                "순수부족량(EA)": f"{max(0, pure_shortage):,}",
                "PLT포장단위": f"{plt_size:,}",
                "이론PLT": f"{exact_plt:.2f}",
                "권고 발주 PLT": f"{final_plt:,} PLT",
                "최종 발주 권고 수량(EA)": f"{final_ea:,} EA"
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
        
        # 엑셀 다운로드 지원
        csv_buffer = io.StringIO()
        df_res.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 발주 결과 엑셀(CSV) 다운로드",
            data=csv_buffer.getvalue().encode("utf-8-sig"),
            file_name=f"{selected_vendor}_n+1월_발주산출결과.csv",
            mime="text/csv",
        )
