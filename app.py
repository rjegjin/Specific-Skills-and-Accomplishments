import streamlit as st
import pandas as pd
import json
import os
from seteuk_core import SeteukEngine
from homeroom_engine import HomeroomEngine
from seteuk_config import INPUT_CSV, SPREADSHEET_ID, SERVICE_ACCOUNT_FILE
from keywords_config import KEYWORD_LIBRARY
from st_aggrid import AgGrid, GridOptionsBuilder
import gspread
from google.oauth2.service_account import Credentials

import random

def get_neis_bytes(text):
    """나이스(NEIS) 기준 바이트 계산 (한글 3바이트, 나머지 1바이트)"""
    if not text: return 0
    count = 0
    for char in text:
        if ord(char) > 127:
            count += 3
        elif char == '\n': # 줄바꿈 처리
            count += 2
        else:
            count += 1
    return count

# 지루함 방지용 메시지 풀
WAITING_MESSAGES = [
    "🍎 선생님, AI가 문장을 정교하게 다듬는 중입니다. 잠시만 기다려 주세요!",
    "💡 생기부 기재 팁: 구체적인 행동과 변화 과정을 중심으로 적으면 더 좋은 생기부가 됩니다.",
    "📚 나이스(NEIS) 입력 시 영문/숫자는 1바이트, 한글은 3바이트로 계산되니 주의하세요!",
    "📝 AI는 현재 선생님의 관찰 팩트를 기반으로 성장 중심 서사를 구성하고 있습니다.",
    "☕️ 잠시 차 한 잔 어떠신가요? 곧 작업이 완료됩니다.",
    "✨ 주어 없이 '~하였음'으로 끝나는 문체는 생기부의 기본입니다.",
    "🔍 생성된 문장에 대학교 이름이나 부모님 직업이 포함되지 않도록 한 번 더 확인해 주세요!"
]

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
                status_text = st.empty()
                course_results = {}
                for prog, name, current_results in course_engine.generate_course_seteuk():
                    status_text.info(f"✨ [{name}] 학생 생성 중... \n\n {random.choice(WAITING_MESSAGES)}")
                    progress_bar.progress(prog)
                    course_results = current_results
                
                # 3. 담임 영역 데이터 수집
                st.write("📥 구글 시트에서 담임 영역 데이터 수집 중...")
                home_data = home_engine.collect_all_data()
                
                # 4. 담임 영역 생성
                st.write("🏠 진로/자율/행종 AI 생성 중...")
                progress_bar_home = st.progress(0)
                status_text_home = st.empty()
                home_results = {}
                for prog, name, current_results in home_engine.generate_homeroom_sections(home_data):
                    status_text_home.info(f"🏠 [{name}] 학생 생성 중... \n\n {random.choice(WAITING_MESSAGES)}")
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
tab0, tab1, tab2, tab3 = st.tabs(["⚡ 실시간 퀵 로그", "📊 데이터 대시보드", "📋 관찰 로그(CSV) 편집", "🔍 AI 생성 결과 프리뷰"])

with tab0:
    st.subheader("⚡ 실시간 키워드 중심 관찰 기록")
    st.markdown("수업 중이나 활동 직후, 학생의 핵심 행동을 키워드 중심으로 즉시 기록합니다.")

    # 구글 시트 연결 (기록용)
    @st.cache_resource
    def get_gspread_client():
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        return gspread.authorize(creds)

    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    
    # 학생 명단 로드 (캐싱)
    @st.cache_data(ttl=600)
    def get_student_names():
        try:
            ws = sh.worksheet("생기부data")
            names = ws.col_values(2)[2:] # 3행부터 성명
            return [n.strip() for n in names if n.strip()]
        except:
            return []

    student_names = get_student_names()

    col_s1, col_s2 = st.columns([1, 2])
    with col_s1:
        selected_name = st.selectbox("👤 학생 선택", ["선택하세요"] + student_names, index=0)
    
    if selected_name != "선택하세요":
        st.divider()
        
        # 3단계 드롭다운 UI
        col_d1, col_d2, col_d3 = st.columns(3)
        
        with col_d1:
            domain_options = list(KEYWORD_LIBRARY.keys())
            selected_domain = st.selectbox("1️⃣ 영역 선택", domain_options)
        
        with col_d2:
            category_options = list(KEYWORD_LIBRARY[selected_domain].keys())
            selected_category = st.selectbox("2️⃣ 대분류 선택", category_options)
            
        with col_d3:
            sub_category_options = list(KEYWORD_LIBRARY[selected_domain][selected_category].keys())
            selected_sub_category = st.selectbox("3️⃣ 중분류 선택", sub_category_options)

        # 최종 키워드 다중 선택
        keyword_pool = KEYWORD_LIBRARY[selected_domain][selected_category][selected_sub_category]
        selected_keywords = st.multiselect("🏷️ 핵심 키워드 선택 (복수 선택 가능)", keyword_pool)
        
        # 추가 상황 기술
        context_input = st.text_area("📝 추가 상황 기술 (구체적 에피소드)", 
                                    placeholder="키워드 외에 구체적인 행동이나 상황이 있다면 적어주세요. AI가 문맥을 만드는 데 큰 도움이 됩니다.",
                                    help="예: '실험 도중 전압계 연결이 잘못된 것을 발견하고 조원들에게 원인을 설명함.'")

        if st.button("🚀 실시간 기록 및 저장", type="primary", use_container_width=True):
            if not selected_keywords and not context_input:
                st.warning("키워드를 선택하거나 내용을 입력해 주세요.")
            else:
                with st.spinner(f"{selected_name} 학생 기록 중..."):
                    try:
                        # 1. 조합된 텍스트 생성
                        combined_fact = ", ".join(selected_keywords)
                        full_entry = f"[{pd.Timestamp.now().strftime('%m/%d')}] {combined_fact}"
                        if context_input:
                            full_entry += f" - {context_input}"

                        # 2. 구글 시트 저장 (생기부data 시트)
                        ws = sh.worksheet("생기부data")
                        all_names = ws.col_values(2)
                        try:
                            row_idx = all_names.index(selected_name) + 1
                            
                            # 영역에 따른 컬럼 결정 (과학: 36열(career_raw 대용 혹은 별도), 담임: 42열 등)
                            # 여기서는 기존 엔진이 사용하는 'career_raw'(36열)와 'behavior_raw'(42열)를 활용
                            col_idx = 36 if "과학" in selected_domain else 42
                            
                            current_val = ws.cell(row_idx, col_idx).value or ""
                            new_val = (current_val + "\n" + full_entry).strip()
                            ws.update_cell(row_idx, col_idx, new_val)
                            
                            # 3. 교과일 경우 CSV에도 추가 (선택사항)
                            if "과학" in selected_domain and os.path.exists(INPUT_CSV):
                                df_logs = pd.read_csv(INPUT_CSV, encoding='utf-8-sig')
                                new_row = {
                                    "날짜": pd.Timestamp.now().strftime('%Y-%m-%d'),
                                    "이름": selected_name,
                                    "대분류(상황)": selected_category,
                                    "소분류(활동)": selected_sub_category,
                                    "구체적 행동(Fact)": context_input if context_input else combined_fact,
                                    "핵심 키워드": combined_fact,
                                    "영향/반응": "긍정적 변화",
                                    "교사 메모": ""
                                }
                                df_logs = pd.concat([df_logs, pd.DataFrame([new_row])], ignore_index=True)
                                df_logs.to_csv(INPUT_CSV, index=False, encoding='utf-8-sig')

                            st.success(f"✅ {selected_name} 학생의 기록이 성공적으로 업데이트되었습니다!")
                            st.toast(f"{selected_name} 기록 완료")
                        except ValueError:
                            st.error(f"시트에서 '{selected_name}' 학생을 찾을 수 없습니다.")
                    except Exception as e:
                        st.error(f"저장 중 오류 발생: {e}")

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
        
        # 바이트 제한 설정 (나이스 기준)
        LIMITS = {"course": 1500, "career": 2100, "autonomous": 1500, "behavior": 1500}
        
        # 복사 상태 관리를 위한 세션 초기화
        if 'copy_status' not in st.session_state:
            st.session_state.copy_status = {}
        
        with col1:
            # 1) 교과 세특
            b_course = get_neis_bytes(res['course'])
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**1) 교과 세부능력** `{b_course}/{LIMITS['course']} bytes`")
            with c2:
                if st.button("📋 복사", key=f"btn_course_{selected_student}"):
                    pyperclip.copy(res['course'])
                    st.toast(f"[{selected_student}] 교과 세특 복사 완료!")
                    st.session_state.copy_status[f"{selected_student}_course"] = True
            
            st.progress(min(b_course / LIMITS['course'], 1.0))
            st.session_state.final_results[selected_student]['course'] = st.text_area("내용 편집", res['course'], height=300, key=f"course_{selected_student}", label_visibility="collapsed")
            
            # 2) 진로활동
            b_career = get_neis_bytes(res['career'])
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**2) 진로활동** `{b_career}/{LIMITS['career']} bytes`")
            with c2:
                if st.button("📋 복사", key=f"btn_career_{selected_student}"):
                    pyperclip.copy(res['career'])
                    st.toast(f"[{selected_student}] 진로활동 복사 완료!")
                    st.session_state.copy_status[f"{selected_student}_career"] = True

            st.progress(min(b_career / LIMITS['career'], 1.0))
            st.session_state.final_results[selected_student]['career'] = st.text_area("내용 편집", res['career'], height=200, key=f"career_{selected_student}", label_visibility="collapsed")
            
        with col2:
            # 3) 자율활동
            b_auto = get_neis_bytes(res['autonomous'])
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**3) 자율활동** `{b_auto}/{LIMITS['autonomous']} bytes`")
            with c2:
                if st.button("📋 복사", key=f"btn_auto_{selected_student}"):
                    pyperclip.copy(res['autonomous'])
                    st.toast(f"[{selected_student}] 자율활동 복사 완료!")
                    st.session_state.copy_status[f"{selected_student}_auto"] = True

            st.progress(min(b_auto / LIMITS['auto_label' if 'auto_label' in locals() else 'autonomous'], 1.0))
            st.session_state.final_results[selected_student]['autonomous'] = st.text_area("내용 편집", res['autonomous'], height=200, key=f"auto_{selected_student}", label_visibility="collapsed")
            
            # 4) 행동특성
            b_behav = get_neis_bytes(res['behavior'])
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**4) 행동특성/종합** `{b_behav}/{LIMITS['behavior']} bytes`")
            with c2:
                if st.button("📋 복사", key=f"btn_behav_{selected_student}"):
                    pyperclip.copy(res['behavior'])
                    st.toast(f"[{selected_student}] 행종 복사 완료!")
                    st.session_state.copy_status[f"{selected_student}_behav"] = True

            st.progress(min(b_behav / LIMITS['behavior'], 1.0))
            st.session_state.final_results[selected_student]['behavior'] = st.text_area("내용 편집", res['behavior'], height=300, key=f"behav_{selected_student}", label_visibility="collapsed")
            
        st.caption(f"💡 위 텍스트박스에서 내용을 직접 수정하면 즉시 반영되며, '구글 시트 전송'을 누르면 저장됩니다.")
    else:
        st.write("생성된 결과가 없습니다.")
