import pandas as pd
import json
import os
import re
from google import genai
import gspread
from google.oauth2.service_account import Credentials
from seteuk_config import *

class SeteukEngine:
    def __init__(self):
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            # [보안 패치] 중앙 .env 로드 로직
            current = Path(os.getcwd())
            env_loaded = False
            while current != current.parent:
                target = current / '.secrets' / '.env'
                if target.exists():
                    load_dotenv(target)
                    print(f"🔐 Loaded central .env from {target}")
                    env_loaded = True
                    break
                current = current.parent
            if not env_loaded: load_dotenv()
        except:
            pass
            
        self.api_key = os.getenv("GEMINI_API_KEY")
        # Streamlit Cloud 대응
        if not self.api_key:
            try:
                import streamlit as st
                self.api_key = st.secrets.get("GEMINI_API_KEY")
            except:
                pass
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or secrets.")
            
        self.client_ai = genai.Client(api_key=self.api_key)
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        self.creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        self.client_sheets = gspread.authorize(self.creds)

    def preprocess(self):
        """질적 연구 기반 교과 데이터 전처리"""
        if not os.path.exists(INPUT_CSV):
            raise FileNotFoundError(f"입력 CSV 파일을 찾을 수 없습니다: {INPUT_CSV}")
            
        # 출력 디렉토리 생성 보장
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        df = pd.read_csv(INPUT_CSV, encoding='utf-8-sig')
        df = df.sort_values(by=['이름', '날짜'])
        structured = {name: group.to_dict('records') for name, group in df.groupby('이름')}
        with open(STRUCTURED_JSON, 'w', encoding='utf-8') as f:
            json.dump(structured, f, ensure_ascii=False, indent=4)
        return len(structured)

    def clean_and_validate(self, text, student_name):
        """군소리 제거 및 금지어 2차 검증 로직"""
        # 1. 마크다운 및 불필요한 패턴 제거
        text = re.sub(r'^\*\*.*?\*\*.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\[.*?\]', '', text, flags=re.MULTILINE)
        text = re.sub(r'^다음은.*?입니다\.?\s*', '', text, flags=re.IGNORECASE)
        
        # 2. 이름 및 호칭 강제 삭제 (이중 안전장치)
        text = text.replace(f"{student_name}은", "").replace(f"{student_name}는", "").replace(f"{student_name}의", "")
        text = text.replace(f"{student_name}", "").replace("이 학생은", "").replace("학생은", "").replace("본인은", "")
        
        # 3. 앞뒤 따옴표 및 공백 정리
        text = text.strip().strip('"').strip("'").strip()
        
        # 4. 문장 시작 조사 보정
        text = re.sub(r'^[은는이가]\s*', '', text)
        
        # 5. 금지어 스캔
        found_prohibited = [kw for kw in PROHIBITED_KEYWORDS if kw in text]
        status = "검증완료"
        if found_prohibited:
            status = f"⚠️금지어주의({','.join(found_prohibited)})"
            
        return text, status

    def generate_course_seteuk(self):
        """교과 세특 AI 생성 (제너레이터 방식)"""
        with open(STRUCTURED_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        results = {}
        total = len(data)
        for i, (name, obs_list) in enumerate(data.items()):
            def get_memo(o):
                return o.get('교사 메모', o.get('교사 메모(추후 종합용)', ''))

            obs_text = "\n".join([f"- {o['대분류(상황)']}: {o['구체적 행동(Fact)']} (키워드: {o['핵심 키워드']}, 메모: {get_memo(o)})" for o in obs_list])
            prompt = f"학생 성명: {name}\n관찰 기록:\n{obs_text}\n\n위 지침에 따라 주어 없이 '~하였음.'으로 끝나는 완벽한 문장만 출력하라."
            
            response = self.client_ai.models.generate_content(
                model='gemini-2.0-flash',
                contents=[SYSTEM_PROMPT, prompt]
            )
            content, status = self.clean_and_validate(response.text.strip(), name)
            results[name] = content
            # 진행률, 현재 학생 이름, 결과 데이터 반환
            yield (i + 1) / total, name, results

    def sync_all(self, final_integrated_data):
        """통합 시트 업로드 (검증 상태 포함)"""
        sh = self.client_sheets.open_by_key(SPREADSHEET_ID)
        try:
            sheet = sh.worksheet("세특최종결과물")
            sheet.clear()
        except:
            sheet = sh.add_worksheet(title="세특최종결과물", rows="100", cols="6")
        
        headers = [["성명", "1) 교과 세부능력(질적분석)", "2) 진로활동", "3) 자율활동", "4) 행동특성/종합", "최종 검증 상태"]]
        sheet.update(values=headers, range_name='A1:F1')
        
        all_rows = []
        for name, data in final_integrated_data.items():
            # 각 영역별 금지어 검증 결과 취합
            status_list = []
            for area in ['course', 'career', 'autonomous', 'behavior']:
                _, status = self.clean_and_validate(data.get(area, ""), name)
                if "⚠️" in status: status_list.append(status)
            
            final_status = "✅ 모든 검사 통과" if not status_list else " | ".join(set(status_list))
            
            all_rows.append([
                name,
                data.get("course", ""),
                data.get("career", ""),
                data.get("autonomous", ""),
                data.get("behavior", ""),
                final_status
            ])
        
        if all_rows:
            sheet.update(values=all_rows, range_name=f'A2:F{len(all_rows)+1}')
            sh.batch_update({"requests": [
                {"updateDimensionProperties": {"range": {"sheetId": sheet.id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 5}, "properties": {"pixelSize": 450}, "fields": "pixelSize"}},
                {"repeatCell": {"range": {"sheetId": sheet.id, "startRowIndex": 1}, "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}}, "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}}
            ]})
        print(f"✅ 총 {len(all_rows)}명의 데이터 검사 및 시트 업로드 완료")