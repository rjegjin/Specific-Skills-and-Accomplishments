import streamlit as st
import pandas as pd
import json
import os
from seteuk_core import SeteukEngine
from homeroom_engine import HomeroomEngine
from seteuk_config import INPUT_CSV, SPREADSHEET_ID
from st_aggrid import AgGrid, GridOptionsBuilder

# 페이지 설정
st.set_page_config(page_title="질적 연구 기반 세특 생성기", layout="wide", page_icon="📝")

st.title("📝 질적 연구 데이터 기반 세특/행종 생성 시스템")
st.markdown("---")

# 세션 상태 초기화
if 'final_results' not in st.session_state:
    st.session_state.final_results = {}

# 사이드바 설정
with st.sidebar:
    st.header("⚙️ 제어판")
    if st.button("🚀 전체 시스템 가동", use_container_width=True):
        status_container = st.container()
        with status_container:
            with st.status("🛠️ AI 생기부 생성 시스템 가동 중...", expanded=True) as status:
                course_engine = SeteukEngine()
                home_engine = HomeroomEngine()
                
                # 1. 교과 데이터 전처리
                try:
                    st.write("📂 교과 데이터 전처리 중...")
                    course_engine.preprocess()
                except Exception as e:
                    st.error(f"전처리 중 오류 발생: {e}")
                    st.stop()
                
                # 2. 교과 세특 생성
                st.write("🧬 교과 세특 AI 생성 중...")
                progress_bar = st.progress(0)
                course_results = {}
                for prog, name, current_results in course_engine.generate_course_seteuk():
                    st.write(f"  - [{name}] 학생 교과 세특 생성 완료")
                    progress_bar.progress(prog)
                    course_results = current_results
                
                # 3. 담임 영역 데이터 수집
                st.write("📥 구글 시트에서 담임 영역 데이터 수집 중...")
                home_data = home_engine.collect_all_data()
                
                # 4. 담임 영역 생성
                st.write("🏠 진로/자율/행종 AI 생성 중...")
                progress_bar_home = st.progress(0)
                home_results = {}
                for prog, name, current_results in home_engine.generate_homeroom_sections(home_data):
                    st.write(f"  - [{name}] 학생 담임 영역 생성 완료")
                    progress_bar_home.progress(prog)
                    home_results = current_results
                
                # 5. 통합 작업
                st.write("🔄 모든 데이터 통합 및 최종 검증 중...")
                all_names = set(course_results.keys()) | set(home_results.keys())
                integrated = {}
                for name in sorted(all_names):
                    integrated[name] = {
                        "course": course_results.get(name, ""),
                        "career": home_results.get(name, {}).get("career", ""),
                        "autonomous": home_results.get(name, {}).get("autonomous", ""),
                        "behavior": home_results.get(name, {}).get("behavior", "")
                    }
                st.session_state.final_results = integrated
                status.update(label="✅ 모든 학생 데이터 생성 완료!", state="complete", expanded=False)
            
            st.balloons()
            st.success("데이터 생성이 성공적으로 완료되었습니다!")

    if st.button("📤 구글 시트 전송", type="primary", use_container_width=True):
        if not st.session_state.final_results:
            st.error("먼저 시스템을 가동하여 데이터를 생성하세요.")
        else:
            with st.spinner("구글 시트 동기화 중..."):
                engine = SeteukEngine()
                engine.sync_all(st.session_state.final_results)
                st.success("업로드 완료!")

    st.markdown("---")
    st.info(f"""📍 연결된 시트 ID:
`{SPREADSHEET_ID}`""")

# 메인 화면 탭 구성
tab1, tab2, tab3 = st.tabs(["📊 데이터 대시보드", "📋 관찰 로그(CSV) 편집", "🔍 AI 생성 결과 프리뷰"])

with tab1:
    st.subheader("📌 작업 현황")
    if st.session_state.final_results:
        df_summary = pd.DataFrame([
            {"성명": k, 
             "교과": "✅" if v['course'] else "❌", 
             "진로": "✅" if v['career'] else "❌",
             "자율": "✅" if v['autonomous'] else "❌",
             "행종": "✅" if v['behavior'] else "❌"} 
            for k, v in st.session_state.final_results.items()
        ])
        st.dataframe(df_summary, use_container_width=True)
    else:
        st.write("시스템 가동 버튼을 눌러 작업을 시작하세요.")

with tab2:
    st.subheader("📝 교과 관찰 로그 편집 (observation_logs.csv)")
    st.markdown("""
    💡 **팁:** 
    - 각 셀을 클릭하여 내용을 수정할 수 있습니다. 
    - '대분류', '소분류', '영향/반응' 컬럼은 드롭다운 메뉴를 지원합니다.
    - 수정 후 반드시 하단의 **'💾 로그 파일 저장'** 버튼을 눌러주세요.
    """)
    
    if os.path.exists(INPUT_CSV):
        df_logs = pd.read_csv(INPUT_CSV, encoding='utf-8-sig')
        
        # 드롭다운 옵션 정의
        options_main = ["수업시간", "쉬는/점심시간", "학급자치/조종례", "동아리활동", "진로활동", "기타"]
        options_sub = ["모둠 협력 활동", "발표 및 토론", "개인 과제", "교우관계/상담", "학급회의 의견 제시", "실험/실습", "기타"]
        options_impact = [
            "수업/활동의 효율을 높임 (긍정)", 
            "문제를 원만히 해결함 (긍정)", 
            "교사에게 깊은 인상을 줌 (긍정)", 
            "학급 분위기를 밝게 만듦 (긍정)",
            "공동체 의식을 발휘함 (긍정)",
            "기타"
        ]

        gb = GridOptionsBuilder.from_dataframe(df_logs)
        gb.configure_default_column(editable=True, resizable=True)
        
        # 특정 컬럼에 드롭다운(Rich Select) 설정
        gb.configure_column("대분류(상황)", editable=True, cellEditor='agRichSelectCellEditor', cellEditorParams={'values': options_main})
        gb.configure_column("소분류(활동)", editable=True, cellEditor='agRichSelectCellEditor', cellEditorParams={'values': options_sub})
        gb.configure_column("영향/반응", editable=True, cellEditor='agRichSelectCellEditor', cellEditorParams={'values': options_impact})
        
        # 날짜 컬럼 너비 조정
        gb.configure_column("날짜", width=120)
        gb.configure_column("이름", width=100)
        
        grid_options = gb.build()
        
        # 행 추가 버튼
        col_btn1, col_btn2 = st.columns([1, 5])
        with col_btn1:
            if st.button("➕ 행 추가", use_container_width=True):
                new_row = pd.DataFrame([[pd.Timestamp.now().strftime('%Y-%m-%d'), "이름", "수업시간", "활동", "내용", "키워드", "영향/반응", "메모"]], 
                                     columns=df_logs.columns)
                df_logs = pd.concat([df_logs, new_row], ignore_index=True)
                df_logs.to_csv(INPUT_CSV, index=False, encoding='utf-8-sig')
                st.rerun()

        grid_response = AgGrid(
            df_logs, 
            gridOptions=grid_options, 
            update_mode='MODEL_CHANGED',
            data_return_mode='FILTERED_AND_SORTED',
            fit_columns_on_grid_load=False,
            theme='streamlit'
        )
        
        if st.button("💾 로그 파일 저장", type="primary"):
            updated_df = pd.DataFrame(grid_response['data'])
            updated_df.to_csv(INPUT_CSV, index=False, encoding='utf-8-sig')
            st.success("✅ CSV 파일이 성공적으로 업데이트되었습니다!")
    else:
        st.error("관찰 로그 파일을 찾을 수 없습니다.")

with tab3:
    st.subheader("🔍 학생별 생성 결과 상세 확인")
    if st.session_state.final_results:
        student_list = list(st.session_state.final_results.keys())
        selected_student = st.selectbox("학생 선택", student_list)
        
        res = st.session_state.final_results[selected_student]
        
        col1, col2 = st.columns(2)
        with col1:
            st.text_area("1) 교과 세부능력(질적분석)", res['course'], height=300)
            st.text_area("2) 진로활동", res['career'], height=200)
        with col2:
            st.text_area("3) 자율활동", res['autonomous'], height=200)
            st.text_area("4) 행동특성/종합의견", res['behavior'], height=300)
            
        st.caption(f"💡 위 텍스트박스에서 내용을 직접 수정하고 '구글 시트 전송'을 누르면 수정본이 올라갑니다.")
    else:
        st.write("생성된 결과가 없습니다.")
