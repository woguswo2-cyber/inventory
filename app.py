if uploaded_file is not None:
    try:
        df = None
        file_name = uploaded_file.name.lower()

        # 1. 파일 확장자 및 엔진별 자동 판독
        if file_name.endswith(".csv"):
            try:
                df = pd.read_csv(uploaded_file, encoding="utf-8")
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding="cp949")
        elif file_name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file, engine="openpyxl")
        elif file_name.endswith(".xls"):
            # 구형 바이너리 xls 시도 -> 실패 시 HTML 텍스트 형식 시도 (ERP 전산 다운로드 호환)
            try:
                uploaded_file.seek(0)
                df = pd.read_excel(uploaded_file, engine="xlrd")
            except Exception:
                try:
                    uploaded_file.seek(0)
                    df = pd.read_html(uploaded_file)[0]
                except Exception:
                    uploaded_file.seek(0)
                    df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        # 2. 열 이름 양끝 공백 제거 및 문자열화
        df.columns = [str(c).strip() for c in df.columns]

        # 3. 데이터 파싱
        part_db = {}
        for _, row in df.iterrows():
            p_no = str(row.get("품번", "")).strip().upper()
            if p_no and p_no != "NAN":
                part_db[p_no] = {
                    "name": str(row.get("품명", "")).strip(),
                    "current_stock": int(row.get("현재재고", 0)) if pd.notna(row.get("현재재고")) else 0,
                    "safety_stock": int(row.get("안전재고", 0)) if pd.notna(row.get("안전재고")) else 0,
                    "moq": int(row.get("MOQ", 0)) if pd.notna(row.get("MOQ")) else 0,
                    "lot_size": int(row.get("LOT", 1)) if pd.notna(row.get("LOT")) else 1,
                }
        st.sidebar.success(f"✅ 총 {len(part_db):,}개 품목 로드 완료")
    except Exception as e:
        st.sidebar.error(f"⚠️ 파일 로드 실패: {e}")
