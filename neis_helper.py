#!/usr/bin/env python3
"""
NEIS Helper — 구글 시트 데이터를 나이스 입력창에 자동으로 붙여넣는 CLI 매크로.

사용법:
  python neis_helper.py                               # 저장된 설정 자동 로드
  python neis_helper.py --setup                       # 대화형 설정 마법사
  python neis_helper.py --sheet <ID_or_URL> \\
      --tab <탭이름> --name <이름열헤더> \\
      --cols 교과세특,진로활동,자율활동,행발종합

단축키:
  F9          붙여넣기 + 다음 학생 이동
  F8          클립보드 복사만 (붙여넣기 X, 미리보기용)
  F7          클립보드의 이름으로 학생 검색·이동
  F10         시트 데이터 새로고침
  Ctrl+↑/↓   학생 위아래 이동
  Ctrl+←/→   열(항목) 변경
  Ctrl+Home   첫 학생으로 이동
  ESC         종료
"""
import argparse
import json
import os
import sys
import time

import keyboard
import pyperclip
from sheets_client import get_client

CONFIG_FILE = os.path.expanduser("~/.neis_helper.json")


# ──────────────────────────────────────────────
#  설정 로드
# ──────────────────────────────────────────────

def parse_sheet_id(raw: str) -> str:
    if "/d/" in raw:
        return raw.split("/d/")[1].split("/")[0]
    return raw.strip()


def run_wizard() -> dict:
    print("\n⚙️  NEIS Helper 초기 설정 마법사")
    sheet_id = parse_sheet_id(input("구글 시트 URL 또는 ID: ").strip())
    tab      = input("시트 탭 이름: ").strip()
    name_col = input("이름 열 헤더 (예: 이름): ").strip() or "이름"
    cols_raw = input("데이터 열 헤더들 (쉼표 구분, 예: 교과세특,진로활동): ").strip()
    cfg = {
        "sheet_id": sheet_id,
        "tab": tab,
        "name_col": name_col,
        "data_cols": [c.strip() for c in cols_raw.split(",") if c.strip()],
    }
    if input(f"\n설정을 {CONFIG_FILE}에 저장할까요? (y/n): ").strip().lower() == "y":
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"✅ 저장 완료: {CONFIG_FILE}")
    return cfg


def load_config(args) -> dict:
    """우선순위: CLI 인자 > 저장된 config 파일 > 마법사"""
    if args.sheet:
        if not args.cols:
            print("❌ --cols 가 필요합니다. 예: --cols 교과세특,진로활동")
            sys.exit(1)
        return {
            "sheet_id": parse_sheet_id(args.sheet),
            "tab": args.tab,
            "name_col": args.name,
            "data_cols": [c.strip() for c in args.cols.split(",")],
        }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        print(f"📂 설정 로드: {CONFIG_FILE}  (덮어쓰려면 --setup)")
        return cfg
    print("설정 파일 없음. 마법사를 시작합니다.")
    return run_wizard()


# ──────────────────────────────────────────────
#  시트 데이터 로드
# ──────────────────────────────────────────────

def load_sheet(cfg: dict):
    print("🌐 시트 데이터 불러오는 중...", end=" ", flush=True)
    client = get_client()
    ws = client.open_by_key(cfg["sheet_id"]).worksheet(cfg["tab"])
    data = ws.get_all_values()
    if not data:
        print("❌ 시트가 비어 있습니다.")
        return [], []

    # raw_idx 모드: 헤더 없이 열 인덱스로 직접 지정
    # cfg 예시: {"layout":"raw_idx","name_idx":4,"data_cols":{"질량보존":7,"등속운동":13},"skip_rows":2}
    if cfg.get("layout") == "raw_idx":
        name_idx = cfg["name_idx"]
        col_map  = cfg["data_cols"]   # {"라벨": 열인덱스, ...}
        valid_cols = list(col_map.keys())
        students = []
        for row in data[cfg.get("skip_rows", 1):]:
            name = row[name_idx].strip() if name_idx < len(row) else ""
            if not name:
                continue
            entry = {"name": name}
            for label, idx in col_map.items():
                entry[label] = row[idx].strip() if idx < len(row) else ""
            students.append(entry)
        print(f"✅ {len(students)}명 / {len(valid_cols)}개 열 로드 완료")
        return students, valid_cols

    # 기본 모드: 헤더 행에서 열 이름으로 찾기
    headers = data[0]

    try:
        name_idx = headers.index(cfg["name_col"])
    except ValueError:
        print(f"\n❌ 이름 열 '{cfg['name_col']}' 을 찾을 수 없습니다.")
        print(f"   시트 헤더: {headers}")
        sys.exit(1)

    col_indices = []
    valid_cols = []
    for col in cfg["data_cols"]:
        try:
            col_indices.append(headers.index(col))
            valid_cols.append(col)
        except ValueError:
            print(f"\n⚠️  열 '{col}' 없음 — 건너뜀")

    students = []
    for row in data[1:]:
        name = row[name_idx].strip() if name_idx < len(row) else ""
        if not name:
            continue
        entry = {"name": name}
        for col, idx in zip(valid_cols, col_indices):
            entry[col] = row[idx].strip() if idx < len(row) else ""
        students.append(entry)

    print(f"✅ {len(students)}명 / {len(valid_cols)}개 열 로드 완료")
    return students, valid_cols


# ──────────────────────────────────────────────
#  UI 헬퍼
# ──────────────────────────────────────────────

def wait_release(key: str):
    while keyboard.is_pressed(key):
        time.sleep(0.05)
    time.sleep(0.1)


def show_status(students, idx, mode_idx, cols):
    name = students[idx]["name"]
    col  = cols[mode_idx]
    total = len(students)
    col_total = len(cols)
    # 내용 미리보기 (30자)
    preview = students[idx].get(col, "")[:30].replace("\n", " ")
    print(
        f"\r 👤 [{idx+1}/{total}] {name}  "
        f"│  📋 [{mode_idx+1}/{col_total}] {col}  "
        f"│  {preview}…   ",
        end="",
        flush=True,
    )


# ──────────────────────────────────────────────
#  메인 루프
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="NEIS 자동 입력 도우미 — 구글 시트 → 나이스 붙여넣기 매크로",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--setup",  action="store_true", help="대화형 설정 마법사 실행")
    parser.add_argument("--sheet",  help="구글 시트 URL 또는 ID")
    parser.add_argument("--tab",    default="Sheet1", help="시트 탭 이름 (기본: Sheet1)")
    parser.add_argument("--name",   default="이름",    help="이름 열 헤더 (기본: 이름)")
    parser.add_argument("--cols",   help="데이터 열 헤더들 (쉼표 구분)")
    args = parser.parse_args()

    if args.setup:
        cfg = run_wizard()
    else:
        cfg = load_config(args)

    students, cols = load_sheet(cfg)
    if not students:
        print("❌ 학생 데이터 없음")
        return

    idx      = 0
    mode_idx = 0
    # 열별 완료/건너뜀 카운터  {"열이름": {"done": 0, "skip": 0}}
    stats = {col: {"done": 0, "skip": 0} for col in cols}

    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 62)
    print("  🚀  NEIS Helper  —  범용 시트 입력 매크로")
    print(f"  📊  {cfg['tab']}  ({cfg['sheet_id'][:20]}…)")
    print("=" * 62)
    print("  F9          붙여넣기 + 다음 학생")
    print("  F8          클립보드 복사만 (미리보기)")
    print("  F7          클립보드 이름으로 학생 검색")
    print("  F10         시트 새로고침")
    print("  Ctrl+↑/↓   학생 이동   │  Ctrl+←/→  열 변경")
    print("  Ctrl+Home   처음으로   │  ESC        종료")
    print("=" * 62)
    show_status(students, idx, mode_idx, cols)

    while True:
        time.sleep(0.01)

        if keyboard.is_pressed("esc"):
            print("\n")
            print("=" * 62)
            print("  📊 세션 요약")
            print("=" * 62)
            for col in cols:
                done = stats[col]["done"]
                skip = stats[col]["skip"]
                total = len(students)
                remain = total - done - skip
                bar = "█" * done + "░" * remain
                print(f"  {col}")
                print(f"    완료 {done:3d}  건너뜀 {skip:2d}  남음 {remain:3d}  [{bar[:30]}]")
            print("=" * 62)
            print("👋 종료합니다.")
            break

        elif keyboard.is_pressed("f10"):
            print()
            students, cols = load_sheet(cfg)
            show_status(students, idx, mode_idx, cols)
            wait_release("f10")

        elif keyboard.is_pressed("f7"):
            name = pyperclip.paste().strip()
            for i, s in enumerate(students):
                if s["name"] == name:
                    idx = i
                    print(f"\n🎯 {name} → {i+1}번")
                    show_status(students, idx, mode_idx, cols)
                    break
            else:
                print(f"\n❌ '{name}' 없음")
            wait_release("f7")

        elif keyboard.is_pressed("f8"):
            content = students[idx].get(cols[mode_idx], "")
            if content:
                pyperclip.copy(content)
                print(f"\n📋 복사됨 ({len(content)}자): {students[idx]['name']}")
            else:
                print(f"\n⚠️  내용 없음: {students[idx]['name']}")
            wait_release("f8")

        elif keyboard.is_pressed("f9"):
            student = students[idx]
            col     = cols[mode_idx]
            content = student.get(col, "")
            if content:
                pyperclip.copy(content)
                keyboard.press_and_release("ctrl+v")
                stats[col]["done"] += 1
                done = stats[col]["done"]
                print(f"\n✅ {student['name']} ({len(content)}자)  [{col} {done}/{len(students)}명]")
            else:
                stats[col]["skip"] += 1
                print(f"\n⚠️  건너뜀: {student['name']} (내용 없음)")
            if idx < len(students) - 1:
                idx += 1
            else:
                print(f"\n🎉 [{col}] 마지막 학생!")
            show_status(students, idx, mode_idx, cols)
            wait_release("f9")

        elif keyboard.is_pressed("ctrl+home"):
            idx = 0
            show_status(students, idx, mode_idx, cols)
            wait_release("home")

        elif keyboard.is_pressed("ctrl+right"):
            mode_idx = (mode_idx + 1) % len(cols)
            show_status(students, idx, mode_idx, cols)
            wait_release("right")

        elif keyboard.is_pressed("ctrl+left"):
            mode_idx = (mode_idx - 1) % len(cols)
            show_status(students, idx, mode_idx, cols)
            wait_release("left")

        elif keyboard.is_pressed("ctrl+down"):
            if idx < len(students) - 1:
                idx += 1
                show_status(students, idx, mode_idx, cols)
            wait_release("down")

        elif keyboard.is_pressed("ctrl+up"):
            if idx > 0:
                idx -= 1
                show_status(students, idx, mode_idx, cols)
            wait_release("up")


if __name__ == "__main__":
    main()
