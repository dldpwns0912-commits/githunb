"""
============================================================
 SANABI & Universal Custom Controller - PC CLI Bridge
============================================================
- 호환 보드: Arduino Pro Micro, Leonardo, Uno, Nano, ESP32 등
- 통신 규격: 115200 bps (X,Y,East,North,South,West,JoySW)
- 게임 엔진: pydirectinput 기반 DirectX 스캔코드 송출
============================================================
"""

import sys
import os
import time
import json
import glob
import threading
import serial
import serial.tools.list_ports
import pydirectinput

# pydirectinput의 기본 딜레이(0.01초)를 0으로 설정하여 인풋 랙 완전 제거
pydirectinput.PAUSE = 0
pydirectinput.FAILSAFE = False

# 기본 설정 파일 경로
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# 기본 세팅 (산나비 최적화)
DEFAULT_CONFIG = {
    "port": "AUTO",
    "baud": 115200,
    "threshold": 120,
    "center_x": 512,
    "center_y": 512,
    "mappings": {
        "joy_up": "w",
        "joy_down": "s",
        "joy_left": "a",
        "joy_right": "d",
        "east": "space",
        "north": "mouse_left",
        "south": "shift",
        "west": "f",
        "sw": "esc"
    }
}

VALID_INPUTS = ["joy_up", "joy_down", "joy_left", "joy_right", "east", "north", "south", "west", "sw"]
MOUSE_KEYS = ["mouse_left", "mouse_right", "mouse_middle"]


class ControllerBridge:
    def __init__(self):
        self.config = self.load_config()
        self.ser = None
        self.running = False
        self.pressed_keys = set()
        self.pressed_mouse = set()

    def load_config(self, filepath=None):
        target = filepath or CONFIG_FILE
        if os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    # 누락된 기본값 보충
                    for k, v in DEFAULT_CONFIG.items():
                        if k not in cfg:
                            cfg[k] = v
                    return cfg
            except Exception as e:
                print(f"[!] 설정 로드 실패 ({e}), 기본값 사용.")
        return json.loads(json.dumps(DEFAULT_CONFIG))

    def save_config(self, filepath=None):
        target = filepath or CONFIG_FILE
        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            print(f"[OK] 설정이 '{os.path.basename(target)}'에 저장되었습니다.")
        except Exception as e:
            print(f"[!] 설정 저장 실패: {e}")

    def get_available_ports(self):
        ports = serial.tools.list_ports.comports()
        return [(p.device, p.description) for p in ports]

    def find_auto_port(self):
        ports = self.get_available_ports()
        if not ports:
            return None
        # Pro Micro / Leonardo / Arduino / CH340 / CP210 키워드 우선 검색
        for dev, desc in ports:
            desc_lower = desc.lower()
            if any(k in desc_lower for k in ["arduino", "pro micro", "leonardo", "ch340", "cp210", "usb serial"]):
                return dev
        return ports[0][0]

    def connect(self):
        target_port = self.config.get("port", "AUTO")
        if target_port.upper() == "AUTO":
            found = self.find_auto_port()
            if not found:
                print("[!] 연결 가능한 시리얼 포트를 찾을 수 없습니다. (보드를 USB에 연결해 주세요)")
                return False
            target_port = found

        baud = self.config.get("baud", 115200)
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(target_port, baud, timeout=0.1)
            # 연결 후 보드 리셋 안정화 대기
            time.sleep(1.0)
            self.ser.reset_input_buffer()
            print(f"[OK] {target_port} ({baud} bps) 에 성공적으로 연결되었습니다.")
            return True
        except Exception as e:
            print(f"[!] {target_port} 연결 실패: {e}")
            self.ser = None
            return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None

    def release_all_inputs(self):
        """종료 시 모든 눌린 키와 마우스를 안전하게 뗌"""
        for k in list(self.pressed_keys):
            try:
                pydirectinput.keyUp(k)
            except Exception:
                pass
        self.pressed_keys.clear()

        for m in list(self.pressed_mouse):
            try:
                btn = m.replace("mouse_", "")
                pydirectinput.mouseUp(button=btn)
            except Exception:
                pass
        self.pressed_mouse.clear()

    def send_input_event(self, target_name, is_pressed):
        mapped = self.config["mappings"].get(target_name)
        if not mapped:
            return

        mapped_lower = mapped.lower()
        if mapped_lower in MOUSE_KEYS:
            btn = mapped_lower.replace("mouse_", "")
            if is_pressed and mapped_lower not in self.pressed_mouse:
                pydirectinput.mouseDown(button=btn)
                self.pressed_mouse.add(mapped_lower)
            elif not is_pressed and mapped_lower in self.pressed_mouse:
                pydirectinput.mouseUp(button=btn)
                self.pressed_mouse.discard(mapped_lower)
        else:
            if is_pressed and mapped_lower not in self.pressed_keys:
                try:
                    pydirectinput.keyDown(mapped_lower)
                    self.pressed_keys.add(mapped_lower)
                except Exception:
                    pass
            elif not is_pressed and mapped_lower in self.pressed_keys:
                try:
                    pydirectinput.keyUp(mapped_lower)
                    self.pressed_keys.discard(mapped_lower)
                except Exception:
                    pass

    def parse_line(self, line):
        """패킷 파싱: X,Y,East,North,South,West,JoySW"""
        parts = line.strip().split(',')
        if len(parts) < 7:
            return None
        try:
            return {
                "x": int(parts[0]),
                "y": int(parts[1]),
                "east": int(parts[2]) == 1,
                "north": int(parts[3]) == 1,
                "south": int(parts[4]) == 1,
                "west": int(parts[5]) == 1,
                "sw": int(parts[6]) == 1
            }
        except ValueError:
            return None

    def run_bridge(self, test_mode=False):
        """실제 게임 입력 송출 루프 또는 테스트 모드"""
        if not self.ser or not self.ser.is_open:
            if not self.connect():
                return

        mode_name = "🎮 게임 모드 (DirectInput 송출 중)" if not test_mode else "🧪 테스트 모드 (키 송출 안 함)"
        print("\n" + "=" * 60)
        print(f" {mode_name}")
        print(" 콘솔로 복귀하려면 [Ctrl + C] 를 누르세요.")
        print("=" * 60 + "\n")

        self.running = True
        cx = self.config.get("center_x", 512)
        cy = self.config.get("center_y", 512)
        th = self.config.get("threshold", 120)

        # 상태 추적기
        current_state = {inp: False for inp in VALID_INPUTS}

        try:
            while self.running:
                if not self.ser or not self.ser.is_open:
                    print("[!] 시리얼 연결이 끊어졌습니다.")
                    break

                raw_line = self.ser.readline().decode('utf-8', errors='ignore')
                if not raw_line:
                    continue

                data = self.parse_line(raw_line)
                if not data:
                    continue

                # 조이스틱 방향 판별 (yVal < cy - th 이면 위)
                joy_up = data["y"] < (cy - th)
                joy_down = data["y"] > (cy + th)
                joy_left = data["x"] < (cx - th)
                joy_right = data["x"] > (cx + th)

                new_state = {
                    "joy_up": joy_up,
                    "joy_down": joy_down,
                    "joy_left": joy_left,
                    "joy_right": joy_right,
                    "east": data["east"],
                    "north": data["north"],
                    "south": data["south"],
                    "west": data["west"],
                    "sw": data["sw"]
                }

                # 키 이벤트 송출
                if not test_mode:
                    for inp in VALID_INPUTS:
                        if new_state[inp] != current_state[inp]:
                            self.send_input_event(inp, new_state[inp])
                            current_state[inp] = new_state[inp]
                else:
                    current_state = new_state

                # 실시간 상태 한 줄 표시
                pressed_list = [inp for inp in VALID_INPUTS if current_state[inp]]
                active_str = ", ".join(f"{inp}->{self.config['mappings'].get(inp, '-')}" for inp in pressed_list)
                if not active_str:
                    active_str = "None"
                sys.stdout.write(f"\r[LIVE] X:{data['x']:4d} Y:{data['y']:4d} | 누른 키: [{active_str:<35}]")
                sys.stdout.flush()

        except KeyboardInterrupt:
            print("\n[!] 루프를 중단하고 복귀합니다.")
        finally:
            self.running = False
            self.release_all_inputs()
            print("\n[OK] 모든 입력이 해제되었습니다.\n")

    def calibrate(self):
        """조이스틱 중심점 자동 캘리브레이션"""
        if not self.ser or not self.ser.is_open:
            if not self.connect():
                return

        print("[...] 조이스틱을 건드리지 말고 가만히 두세요. 중심점 측정 중...")
        samples_x = []
        samples_y = []
        for _ in range(30):
            line = self.ser.readline().decode('utf-8', errors='ignore')
            data = self.parse_line(line)
            if data:
                samples_x.append(data["x"])
                samples_y.append(data["y"])
            time.sleep(0.02)

        if samples_x and samples_y:
            avg_x = int(sum(samples_x) / len(samples_x))
            avg_y = int(sum(samples_y) / len(samples_y))
            self.config["center_x"] = avg_x
            self.config["center_y"] = avg_y
            print(f"[OK] 중심점 캘리브레이션 완료: Center X={avg_x}, Center Y={avg_y}")
            self.save_config()
        else:
            print("[!] 데이터를 읽어오지 못했습니다. 연결을 확인하세요.")


def print_banner():
    print("""
============================================================
      SANABI & Universal Custom Controller CLI v1.0
          (Pro Micro / Leonardo / Uno / Nano 호환)
============================================================
* 도움말은 'help'를 입력하세요.
* 컨트롤러 바로 시작: 'start' 또는 'run'
============================================================
""")


def print_help():
    print("""
[ 사용 가능한 명령어 목록 ]
 1. 키 매핑
    - bind <버튼> <키>      : 버튼에 키보드/마우스 키 할당
      예: bind north mouse_left  (North버튼 -> 사슬팔 발사)
      예: bind east space        (East버튼 -> 점프)
      예: bind south shift       (South버튼 -> 대시/감기)
    - unbind <버튼>         : 해당 버튼 매핑 해제

 2. 감도 및 장치 설정
    - set threshold <숫자>  : 조이스틱 감도/임계치 조절 (기본: 120)
    - set port <포트명>     : COM 포트 수동 지정 (예: set port COM3, set port AUTO)
    - set baud <속도>       : 시리얼 통신 속도 (기본: 115200)
    - calibrate             : 조이스틱 현재 위치를 중앙(Center)으로 자동 보정
    - ports                 : 현재 PC에 연결된 COM 포트 목록 확인

 3. 실행 및 테스트
    - start (또는 run)      : 산나비 게임 입력 송출 시작 (종료: Ctrl+C)
    - test                  : 키 송출 없이 센서 작동만 확인하는 테스트 모드

 4. 상태 및 프로필 관리
    - status (또는 show)    : 현재 키 매핑과 설정값 표로 확인
    - keys                  : 등록 가능한 특수키/마우스 키 목록 확인
    - save [이름]           : 설정 저장 (예: save sanabi)
    - load [이름]           : 설정 불러오기 (예: load sanabi)
    - profiles              : 저장된 프로필 목록 확인
    - exit (또는 quit)      : 프로그램 종료
""")


def print_status(bridge):
    cfg = bridge.config
    print("\n[ 현재 컨트롤러 설정 ]")
    print(f" * COM 포트    : {cfg.get('port', 'AUTO')} (현재 속도: {cfg.get('baud', 115200)} bps)")
    print(f" * 조이스틱 감도: Threshold={cfg.get('threshold', 120)}, Center=({cfg.get('center_x', 512)}, {cfg.get('center_y', 512)})")
    print("┌────────────────────┬────────────────────┬────────────────────────┐")
    print("│ 하드웨어 입력 항목 │ 현재 매핑된 키     │ 설명 / 산나비 기본 동작│")
    print("├────────────────────┼────────────────────┼────────────────────────┤")
    desc_map = {
        "joy_up": "조이스틱 위 (W)",
        "joy_down": "조이스틱 아래 (S)",
        "joy_left": "조이스틱 좌 (A)",
        "joy_right": "조이스틱 우 (D)",
        "east": "East 버튼 / 점프 (Space)",
        "north": "North 버튼 / 사슬팔 (Mouse_L)",
        "south": "South 버튼 / 대시 (Shift)",
        "west": "West 버튼 / 상호작용 (F)",
        "sw": "조이스틱 클릭 (ESC)"
    }
    for inp in VALID_INPUTS:
        key = cfg["mappings"].get(inp, "(미설정)")
        desc = desc_map.get(inp, "")
        print(f"│ {inp:<18} │ {key:<18} │ {desc:<22} │")
    print("└────────────────────┴────────────────────┴────────────────────────┘\n")


def print_keys():
    print("""
[ 지원하는 키 목록 ]
- 마우스 키: mouse_left, mouse_right, mouse_middle
- 특수 키  : space, shift, ctrl, alt, esc, enter, tab, backspace, caps_lock
- 방향 키  : up, down, left, right
- 문자/숫자: a ~ z, 0 ~ 9, f1 ~ f12
""")


def main():
    bridge = ControllerBridge()
    print_banner()

    # 실행 시 백그라운드로 자동 연결 시도
    bridge.connect()

    while True:
        try:
            line = input("SANABI> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n프로그램을 종료합니다.")
            bridge.disconnect()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ["exit", "quit", "q"]:
            print("프로그램을 종료합니다.")
            bridge.disconnect()
            break

        elif cmd == "help":
            print_help()

        elif cmd in ["status", "show"]:
            print_status(bridge)

        elif cmd == "keys":
            print_keys()

        elif cmd in ["start", "run"]:
            bridge.run_bridge(test_mode=False)

        elif cmd == "test":
            bridge.run_bridge(test_mode=True)

        elif cmd == "ports":
            ports = bridge.get_available_ports()
            print("\n[ 사용 가능한 COM 포트 목록 ]")
            if not ports:
                print(" - 연결된 포트가 없습니다.")
            else:
                for dev, desc in ports:
                    print(f" - {dev}: {desc}")
            print()

        elif cmd == "calibrate":
            bridge.calibrate()

        elif cmd == "bind":
            if len(args) < 2:
                print("[!] 사용법: bind <버튼> <키>  (예: bind north mouse_left)")
                print(f"    가능한 버튼: {', '.join(VALID_INPUTS)}")
                continue
            target, key = args[0].lower(), args[1].lower()
            if target not in VALID_INPUTS:
                print(f"[!] 유효하지 않은 버튼입니다: {target}")
                print(f"    가능한 버튼: {', '.join(VALID_INPUTS)}")
                continue
            bridge.config["mappings"][target] = key
            print(f"[OK] '{target}' -> '{key}' 로 매핑되었습니다.")
            bridge.save_config()

        elif cmd == "unbind":
            if len(args) < 1:
                print("[!] 사용법: unbind <버튼>")
                continue
            target = args[0].lower()
            if target in bridge.config["mappings"]:
                del bridge.config["mappings"][target]
                print(f"[OK] '{target}' 매핑이 해제되었습니다.")
                bridge.save_config()
            else:
                print(f"[!] '{target}'에 설정된 매핑이 없습니다.")

        elif cmd == "set":
            if len(args) < 2:
                print("[!] 사용법: set <옵션> <값>  (예: set threshold 120, set port COM3)")
                continue
            opt, val = args[0].lower(), args[1]
            if opt == "threshold":
                try:
                    bridge.config["threshold"] = int(val)
                    print(f"[OK] Threshold(감도)가 {val} 로 설정되었습니다.")
                    bridge.save_config()
                except ValueError:
                    print("[!] 숫자를 입력해야 합니다.")
            elif opt == "port":
                bridge.config["port"] = val.upper()
                print(f"[OK] 포트가 '{val.upper()}' 로 설정되었습니다. 재연결을 시도합니다...")
                bridge.connect()
                bridge.save_config()
            elif opt == "baud":
                try:
                    bridge.config["baud"] = int(val)
                    print(f"[OK] 통신 속도가 {val} bps로 설정되었습니다.")
                    bridge.connect()
                    bridge.save_config()
                except ValueError:
                    print("[!] 숫자를 입력해야 합니다.")
            else:
                print(f"[!] 알 수 없는 옵션입니다: {opt}")

        elif cmd == "save":
            name = args[0] if args else "config"
            if not name.endswith(".json"):
                name += ".json"
            target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
            bridge.save_config(target_path)

        elif cmd == "load":
            if not args:
                print("[!] 사용법: load <프로필이름>  (예: load sanabi)")
                continue
            name = args[0]
            if not name.endswith(".json"):
                name += ".json"
            target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
            if not os.path.exists(target_path):
                print(f"[!] 프로필 파일을 찾을 수 없습니다: {name}")
                continue
            bridge.config = bridge.load_config(target_path)
            print(f"[OK] '{name}' 프로필을 불러왔습니다.")
            print_status(bridge)

        elif cmd == "profiles":
            folder = os.path.dirname(os.path.abspath(__file__))
            p_files = glob.glob(os.path.join(folder, "*.json"))
            print("\n[ 저장된 프로필 목록 ]")
            for pf in p_files:
                print(f" - {os.path.basename(pf)}")
            print()

        else:
            print(f"[!] 알 수 없는 명령어입니다: '{cmd}'. 'help'를 입력해 보세요.")


if __name__ == "__main__":
    main()
