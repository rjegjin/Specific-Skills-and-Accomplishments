import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import os
import json
import re
from google import genai
from seteuk_config import SERVICE_ACCOUNT_FILE, SPREADSHEET_ID, PROHIBITED_KEYWORDS
from homeroom_config import PROMPT_CAREER, PROMPT_AUTONOMOUS, PROMPT_BEHAVIOR

class HomeroomEngine:
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
            if not env_loaded: load_dotenv() # Fallback
        except:
            pass
            
        self.api_key = os.getenv("GEMINI_API_KEY")
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
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        self.client_sheets = gspread.authorize(creds)
        self.sh = self.client_sheets.open_by_key(SPREADSHEET_ID)

    def get_individual_roles(self):
        """'1인 1역' 시트 비정형 스캔"""
        try:
            ws = self.sh.worksheet("1인 1역")
            data = ws.get_all_values()
            role_map = {}
            for row in data:
                for i in range(len(row)-1):
                    val = str(row[i]).strip()
                    next_val = str(row[i+1]).strip()
                    if 2 <= len(val) <= 4 and next_val and ("역" in next_val or "도우미" in next_val or "부장" in next_val):
                        role_map[val] = next_val
            return role_map
        except:
            return {}

    def collect_all_data(self):
        """담임 영역 통합 데이터 수집"""
        student_data = {}
        roles = self.get_individual_roles()

        ws_data = self.sh.worksheet("생기부data")
        rows = ws_data.get_all_values()
        for row in rows[2:]:
            if len(row) < 42: continue
            name = row[1].strip()
            if not name: continue
            student_data[name] = {
                "dream": row[2],
                "major": row[13],
                "career_raw": row[35],
                "behavior_raw": row[41],
                "role": roles.get(name, "학급 구성원")
            }

        try:
            ws_target = self.sh.worksheet("진학희망교")
            rows_target = ws_target.get_all_values()
            for row in rows_target[1:]:
                if len(row) < 16: continue
                name = row[2].strip()
                if name in student_data:
                    student_data[name]["target_school"] = row[7]
                    student_data[name]["target_note"] = row[15]
        except:
            pass

        try:
            ws_auto = self.sh.worksheet("자율 종합(Random)")
            rows_auto = ws_auto.get_all_values()
            for row in rows_auto[1:]:
                if len(row) < 10: continue
                name = row[8].strip()
                if name in student_data:
                    student_data[name]["auto_content"] = row[9]
        except:
            pass

        return student_data

    def generate_homeroom_sections(self, student_data):
        """담임 영역 AI 생성 및 금지어/맞춤법 검증 (제너레이터 방식)"""
        results = {}
        total = len(student_data)
        for i, (name, data) in enumerate(student_data.items()):
            def call_ai_with_check(system_instr, user_input):
                resp = self.client_ai.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=[system_instr, user_input]
                )
                return resp.text.strip()

            career_text = call_ai_with_check(PROMPT_CAREER, f"이름:{name}, 꿈:{data['dream']}, 전공:{data['major']}, 기록:{data['career_raw']}")
            auto_text = call_ai_with_check(PROMPT_AUTONOMOUS, f"이름:{name}, 역할:{data['role']}, 활동:{data.get('auto_content','')}")
            behave_text = call_ai_with_check(PROMPT_BEHAVIOR, f"이름:{name}, 역할:{data['role']}, 관찰:{data['behavior_raw']}")

            def clean_and_validate(text, student_name):
                # 1. 정제
                text = re.sub(r'^\*\*.*?\*\*.*', '', text, flags=re.MULTILINE)
                text = re.sub(r'^\[.*?\]', '', text, flags=re.MULTILINE)
                text = text.replace(f"{student_name}은", "").replace(f"{student_name}는", "").replace(f"{student_name}의", "")
                text = text.replace(f"{student_name}", "").replace("이 학생은", "").replace("학생은", "").strip()
                text = text.strip('"').strip("'")
                text = re.sub(r'^[은는이가]\s*', '', text)

                # 2. 금지어 체크
                found_prohibited = [kw for kw in PROHIBITED_KEYWORDS if kw in text]
                if found_prohibited:
                    text = f"[⚠️금지어주의: {', '.join(found_prohibited)}] " + text
                return text

            results[name] = {
                "career": clean_and_validate(career_text, name),
                "autonomous": clean_and_validate(auto_text, name),
                "behavior": clean_and_validate(behave_text, name)
            }
            # 진행률, 현재 학생 이름, 결과 데이터 반환
            yield (i + 1) / total, name, results
