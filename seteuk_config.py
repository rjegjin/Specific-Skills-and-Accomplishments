import os
import json

# [환경 및 인증]
# Streamlit Cloud 환경 대응: st.secrets가 있으면 이를 사용하여 임시 키 파일 생성
try:
    import streamlit as st
    if "gcp_service_account" in st.secrets:
        SERVICE_ACCOUNT_FILE = "service_key_cloud.json"
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            with open(SERVICE_ACCOUNT_FILE, "w") as f:
                json.dump(dict(st.secrets["gcp_service_account"]), f)
    else:
        SERVICE_ACCOUNT_FILE = "/home/rjegj/projects/.secrets/service_key.json"
except:
    SERVICE_ACCOUNT_FILE = "/home/rjegj/projects/.secrets/service_key.json"

SPREADSHEET_ID = "1mqlzFYHm2ipo3MYvNCeo6zsNT7-bJ7tEGIsXqYRV7DI"

# [경로 설정]
BASE_DIR = "세특"
INPUT_CSV = os.path.join(BASE_DIR, "observation_logs.csv")
STRUCTURED_JSON = os.path.join(BASE_DIR, "structured_observations.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "qualitative_seteuk_output")

# [나이스 기재 금지 키워드 요목화]
PROHIBITED_KEYWORDS = [
    # 1. 교외 활동 및 수상
    "대학교", "대학원", "교외", "외부", "상장", "수상", "1위", "우승", "금상", "은상", "동상",
    # 2. 공인 시험 및 자격증
    "토익", "TOEIC", "토플", "TOEFL", "텝스", "TEPS", "HSK", "JLPT", "자격증", "영재원",
    # 3. 사회경제적 지위 암시
    "아버지", "어머니", "부모", "교수", "의사", "변호사", "회장님", "학원", "과외",
    # 4. 기타 금지 표현
    "매우", "너무", "최고의", "천재적인" # 주관적 미사여구 지양
]

# [AI 시스템 프롬프트 - 불변의 원칙 적용]
SYSTEM_PROMPT = """
당신은 대한민국 고등학교의 생기부 작성 전문가이자 국어 교열 전문가입니다. 
제공된 데이터를 분석하여 다음 [불변의 원칙]을 준수하여 작성하십시오.

[불변의 원칙 - 위반 시 전체 데이터 파손]
1. 문체 통일: 모든 문장은 반드시 '~하였음.'으로 종결하십시오. (예: '~하였음.', '~보였음.')
2. 호칭 금지: 문장에 'OO 학생', '이 학생', '이름', '본인' 등 어떤 호칭도 넣지 마십시오. 주어 없이 활동으로 시작하십시오.
3. 군소리 제거: "다음은 내용입니다" 등 서론/결론/인사를 절대 적지 마십시오. 오직 순수 본문만 출력하십시오.
4. 마크다운 금지: **볼드체**, [대괄호태그], 따옴표("")를 절대 사용하지 마십시오.

[신규 검증 지침]
5. 기재 금지어 배제: 대학교, 수상, 부모 직업, 학원 등 나이스 기재 금지 사항을 절대 포함하지 마십시오.
6. 완벽한 교열: 문장을 완성한 후 스스로 오자, 탈자, 비문, 띄어쓰기를 3회 검수하여 완벽한 표준어 문장만 출력하십시오.
"""