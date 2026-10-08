/*
 * ============================================================
 *  SANABI Custom Controller - Arduino Pro Micro Firmware
 * ============================================================
 *  보드: Arduino Pro Micro (ATmega32U4, 5V/16MHz)
 *  
 *  핀 구성:
 *   - 조이스틱 X축: A0
 *   - 조이스틱 Y축: A1
 *   - 조이스틱 스위치 (SW): 디지털 2번 핀
 *   - East 버튼: 디지털 7번 핀
 *   - North 버튼: 디지털 6번 핀
 *   - South 버튼: 디지털 8번 핀
 *   - West 버튼: 디지털 5번 핀
 *
 *  통신 속도: 115200 bps
 *  패킷 포맷: X,Y,East,North,South,West,JoySW
 *  예시: 512,504,0,0,0,0,0 (버튼 눌림=1, 뗌=0)
 * ============================================================
 */

// 핀 번호 정의
const int PIN_JOY_X   = A0;
const int PIN_JOY_Y   = A1;
const int PIN_JOY_SW  = 2;

const int PIN_BTN_EAST  = 7;
const int PIN_BTN_NORTH = 6;
const int PIN_BTN_SOUTH = 8;
const int PIN_BTN_WEST  = 5;

// 전송 주기 설정 (약 100Hz = 10ms 주기, 입력 지연 최소화)
const unsigned long SEND_INTERVAL_MS = 10;
unsigned long lastSendTime = 0;

void setup() {
  // 시리얼 통신 초기화 (Pro Micro의 USB CDC 고속 통신)
  Serial.begin(115200);

  // 내부 풀업 저항 활성화 (버튼을 누르면 접지(GND)되어 LOW가 됨)
  pinMode(PIN_BTN_EAST,  INPUT_PULLUP);
  pinMode(PIN_BTN_NORTH, INPUT_PULLUP);
  pinMode(PIN_BTN_SOUTH, INPUT_PULLUP);
  pinMode(PIN_BTN_WEST,  INPUT_PULLUP);
  pinMode(PIN_JOY_SW,    INPUT_PULLUP);

  // 부팅 안정화 대기
  delay(200);
}

void loop() {
  unsigned long currentTime = millis();

  // 10ms 주기로 PC에 센서 상태 전송
  if (currentTime - lastSendTime >= SEND_INTERVAL_MS) {
    lastSendTime = currentTime;

    // 조이스틱 아날로그 값 읽기 (0 ~ 1023)
    int joyX = analogRead(PIN_JOY_X);
    int joyY = analogRead(PIN_JOY_Y);

    // 디지털 버튼 값 읽기 (INPUT_PULLUP: 누르면 0 -> 반전하여 누름=1, 뗌=0)
    int btnEast  = !digitalRead(PIN_BTN_EAST);
    int btnNorth = !digitalRead(PIN_BTN_NORTH);
    int btnSouth = !digitalRead(PIN_BTN_SOUTH);
    int btnWest  = !digitalRead(PIN_BTN_WEST);
    int joySW    = !digitalRead(PIN_JOY_SW);

    // CSV 포맷 전송: X,Y,East,North,South,West,JoySW
    Serial.print(joyX);
    Serial.print(',');
    Serial.print(joyY);
    Serial.print(',');
    Serial.print(btnEast);
    Serial.print(',');
    Serial.print(btnNorth);
    Serial.print(',');
    Serial.print(btnSouth);
    Serial.print(',');
    Serial.print(btnWest);
    Serial.print(',');
    Serial.println(joySW);
  }
}
