import gspread
import pandas as pd
import keyboard
import pyperclip
import time
import os
import sys
from google.oauth2.service_account import Credentials

# 세특 프로젝트 경로 추가 및 설정 로드
sys.path.append(os.path.join(os.getcwd(), '세특'))
try:
    from seteuk_config import SERVICE_ACCOUNT_FILE, SPREADSHEET_ID
except ImportError:
    print("❌ 세특 설정을 찾을 수 없습니다. 경로를 확인해주세요.")
    sys.exit()

# 모드 리스트 (구글 시트 컬럼 순서에 맞춤)
MODES = [
    {"key": "course",     "name": "교과세특(C열)", "col_idx": 2}, 
    {"key": "career",     "name": "진로활동(D열)", "col_idx": 3},
    {"key": "autonomous", "name": "자율활동(E열)", "col_idx": 4},
    {"key": "behavior",   "name": "행발종합(F열)", "col_idx": 5}
]

def load_sheet_data():
    print("🌐 구글 스프레드시트에서 데이터를 가져오는 중...")
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        client = gspread.authorize(creds)
        sh = client.open_by_key(SPREADSHEET_ID)
        
        # '세특최종결과물' 탭 읽기 (또는 적절한 탭 이름)
        ws = sh.worksheet("세특최종결과물")
        data = ws.get_all_values()
        
        headers = data[0]
        rows = data[1:]
        
        students = []
        for row in rows:
            if not row[1].strip(): continue # 이름 없으면 스킵
            student_data = {'name': row[1]}
            for mode in MODES:
                try:
                    content = row[mode["col_idx"]]
                    student_data[mode["key"]] = str(content).strip()
                except IndexError:
                    student_data[mode["key"]] = ""
            students.append(student_data)
        return students
    except Exception as e:
        print(f"❌ 데이터 로드 오류: {e}")
        return []

def wait_key_release(key_name):
    while keyboard.is_pressed(key_name):
        time.sleep(0.05)
    time.sleep(0.1)

def main():
    students = load_sheet_data()
    if not students:
        print("❌ 표시할 학생 데이터가 없습니다.")
        return

    current_mode_idx = 0
    current_idx = 0
    current_mode = MODES[current_mode_idx]
    
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*60)
    print(f" 🚀 [Modern NEIS Helper] 구글 시트 연동 모드")
    print(f" 🔗 연결된 시트: {SPREADSHEET_ID}")
    print("="*60)
    print(" ● [     F9     ] : 붙여넣기 + 다음 유효 학생 이동")
    print(" ● [     F10    ] : 구글 시트 데이터 새로고침")
    print(" ● [     F7     ] : 클립보드 이름으로 학생 검색")
    print(" ↕ [ Ctrl + ↑/↓ ] : 수동 학생 변경")
    print(" ↔ [ Ctrl + ←/→ ] : 입력 항목 변경 (교과/진로/자율/행발)")
    print(" 🏠 [ Ctrl+Home  ] : 맨 처음으로")
    print(" ❌ [     ESC    ] : 종료")
    print("="*60)
    print(f" ✨ 현재 모드: [{current_mode['name']}]")
    print(f" 👤 현재 학생: [{students[current_idx]['name']}]")

    while True:
        time.sleep(0.01)

        if keyboard.is_pressed('esc'):
            print("\n👋 프로그램을 종료합니다.")
            break
            
        elif keyboard.is_pressed('f10'):
            print("\n🔄 데이터를 새로고침합니다...")
            students = load_sheet_data()
            print(f"✅ {len(students)}명의 데이터를 다시 불러왔습니다.")
            wait_key_release('f10')

        elif keyboard.is_pressed('f7'):
            search_name = pyperclip.paste().strip()
            found = False
            for i, s in enumerate(students):
                if s['name'] == search_name:
                    current_idx = i
                    found = True
                    print(f"\n🎯 검색 성공: [{s['name']}] 학생으로 이동했습니다.")
                    break
            if not found:
                print(f"\n❌ 검색 실패: '{search_name}' 학생을 찾을 수 없습니다.")
            wait_key_release('f7')

        elif keyboard.is_pressed('ctrl+home'):
            current_idx = 0
            print(f"\n🏠 처음으로 이동: {students[current_idx]['name']}")
            wait_key_release('home')

        elif keyboard.is_pressed('ctrl+right'):
            current_mode_idx = (current_mode_idx + 1) % len(MODES)
            current_mode = MODES[current_mode_idx]
            print(f"
👉 모드 변경: [ {current_mode['name']} ]")
            wait_key_release('right')

        elif keyboard.is_pressed('ctrl+left'):
            current_mode_idx = (current_mode_idx - 1) % len(MODES)
            current_mode = MODES[current_mode_idx]
            print(f"
👈 모드 변경: [ {current_mode['name']} ]")
            wait_key_release('left')

        elif keyboard.is_pressed('f9'):
            if current_idx < len(students):
                student = students[current_idx]
                content = student[current_mode["key"]]
                
                if content:
                    pyperclip.copy(content)
                    keyboard.press_and_release('ctrl+v')
                    print(f" ✅ [입력 성공] {student['name']}")
                else:
                    print(f" ⚠️ [건너뜀] {student['name']} (내용 없음)")
                
                # 다음 학생으로 이동
                if current_idx < len(students) - 1:
                    current_idx += 1
                    print(f" ⏩ 다음 학생: {students[current_idx]['name']}")
                else:
                    print(f" 🎉 [{current_mode['name']}] 마지막 학생입니다!")
            wait_key_release('f9')

        elif keyboard.is_pressed('ctrl+down'):
            if current_idx < len(students) - 1:
                current_idx += 1
                print(f" ⬇ [아래] {students[current_idx]['name']}")
            wait_key_release('down')

        elif keyboard.is_pressed('ctrl+up'):
            if current_idx > 0:
                current_idx -= 1
                print(f" ⬆ [위] {students[current_idx]['name']}")
            wait_key_release('up')

if __name__ == "__main__":
    main()
