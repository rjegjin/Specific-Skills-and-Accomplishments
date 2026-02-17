from seteuk_core import SeteukEngine
from homeroom_engine import HomeroomEngine

def main():
    course_engine = SeteukEngine()
    home_engine = HomeroomEngine()
    
    # 1. 교과 데이터 처리 (질적 연구 기반)
    print("🚀 1단계: 교과 세특(질적 분석) 데이터 전처리 중...")
    course_count = course_engine.preprocess()
    course_results = {}
    if course_count > 0:
        print(f"   - {course_count}명의 교과 관찰 기록 분석 및 AI 생성 중...")
        # 제너레이터를 리스트/딕셔너리로 변환하여 마지막 결과 획득
        for prog, name, current_results in course_engine.generate_course_seteuk():
            course_results = current_results
    
    # 2. 담임 영역 처리 (시트 데이터 기반)
    print("\n🚀 2단계: 담임 영역(진로/자율/행종) 시트 데이터 취합 중...")
    home_data = home_engine.collect_all_data()
    print(f"   - {len(home_data)}명의 담임 영역 데이터 분석 및 AI 생성 중...")
    # 제너레이터를 리스트/딕셔너리로 변환하여 마지막 결과 획득
    home_results = {}
    for prog, name, current_results in home_engine.generate_homeroom_sections(home_data):
        home_results = current_results
    
    # 3. 데이터 통합 (이름 기준 매칭)
    print("\n🚀 3단계: 모든 영역 데이터 통합 중...")
    final_integrated_data = {}
    
    # 모든 학생 리스트 추출 (교과 데이터 + 담임 데이터 합집합)
    all_student_names = set(course_results.keys()) | set(home_results.keys())
    
    for name in sorted(all_student_names):
        final_integrated_data[name] = {
            "course": course_results.get(name, ""),
            "career": home_results.get(name, {}).get("career", ""),
            "autonomous": home_results.get(name, {}).get("autonomous", ""),
            "behavior": home_results.get(name, {}).get("behavior", "")
        }
    
    # 4. 최종 동기화
    print("\n🚀 4단계: 구글 스프레드시트 최종 통합 업로드 중...")
    course_engine.sync_all(final_integrated_data)
    
    print("\n✨ [완료] 교과 및 담임 영역 통합 세특 생성이 마무리되었습니다!")
    print("🔗 구글 시트의 '세특최종결과물' 탭을 확인해 보세요.")

if __name__ == "__main__":
    main()