# idle-obelisk-macro

LD플레이어에서 실행하는 Idle Obelisk Miner 자동 수령 매크로입니다. ADB로 화면을 캡처하고 OpenCV로 인식해서 탭하므로, 게임 창이 다른 창에 가려져 있어도 동작합니다.

| 기능 | 상태 |
|---|---|
| Lootbug: 루트버그 탭, 설정한 버프만 체크해서 Buy Checked, 팝업 닫기 | 사용 가능 |
| Freebie: 상점 버튼의 초록 막대 확인, 상점 스크롤로 Freebie Pack 찾기, Claim, 상점 닫기 | 사용 가능 |
| Bombs: 폭탄 가방을 열고 고른 순서대로 Gem, Cherry, Battery, D20을 Fire All, 가방 닫기 | 사용 가능 (실기 확인 전) |

## 준비

1. LD플레이어 설정
   - 해상도: 휴대폰 **540×960** (세로, 권장) 또는 720×1280. 다른 해상도면 시작할 때 오류가 납니다.
     게임은 540×960으로 그리고, 720×1280에서는 LD플레이어가 4칸 중 한 칸을 복제해 늘릴 뿐이라 더 선명해지지 않습니다.
     540×960이면 매크로가 같은 방식으로 720×1280 화면을 만들어 인식하고 탭 좌표는 0.75배로 보냅니다.
     캡처 데이터가 약 44% 작아지고 LD플레이어의 그리기 부담도 줄어듭니다.
   - 기타 설정 → ADB 디버깅 → **로컬 연결 열기**
2. Python 3.11 이상에서 패키지 설치
   ```
   pip install -r requirements.txt
   ```
3. LD플레이어가 기본 경로(`C:\LDPlayer\LDPlayer9`)가 아니면, 한 번 실행한 뒤 생기는 `config.json`에서 `adb.path`를 고쳐주세요.

## 실행

```
python main.py
```

- **Home**: 왼쪽에 로그가 올라오고, 오른쪽 아래 `Run`으로 시작하고 멈춥니다. F8을 누르면 언제든 정지합니다.
  문제 로그(아래 "예외 상황")에는 앞에 `[!]`가 붙습니다.
  오른쪽의 **Debug**를 켜면 로그마다 화면을 메모리에 잠시 쌓아 두고, 한 작업(루트버그 한 주기, 프리비 한 주기, 설정 확인 한 번) 안에서 문제 로그가 나오면 그 작업의 처음부터 끝까지 화면을 `debug/로그ID.png`로 저장합니다. `debug/debug.log`에는 작업마다 `----`로 구분해 ID와 로그를 남깁니다. 문제 없이 끝난 작업의 화면은 저장하지 않습니다. 쌓아 두는 동안에는 PNG로 압축해 화면 한 장이 약 0.2MB입니다.
  오른쪽에는 상태(실행 중/정지, 실행 시간, 기기, 캡처 방식과 횟수, 메모리)와 수치 표(이번 실행 / 누적)가 1초마다 갱신됩니다.
  - Lootbug: 수령 횟수, 버프별 구매 수, 실패(팝업 안 열림 / 체크 반영 안 됨 / 구매 보류 / 구매 안 됨), 마지막 수령, 다음 확인까지 남은 시간
  - Freebie: 받은 프리비 개수(Claim 전 `Banked: N/최대`에서 읽음), 실패(상점 진입 / Pack 못 찾음 / Claim / 개수 읽기), 마지막 수령, 다음 확인
  - 누적은 `stats.json`(git 제외)에 저장되어 앱을 껐다 켜도 유지되며, `누적 초기화`로 지울 수 있습니다.
- **연속 캡처(영상)**: Home 오른쪽 Options에서 켭니다. 다음 Run부터 적용됩니다. 아래 "캡처와 메모리" 참고.
- 로그는 화면과 함께 `logs/macro.log`에도 남습니다 (1MB가 넘으면 `.1`로 바꾸고 새로 씀).
- **Setup**: 매크로에 필요한 게임 설정을 확인하고 맞춥니다 (아래 참고). 매크로 실행 중에는 쓸 수 없습니다.
- **Lootbug**: 사용 여부, 구매할 버프, 확인 주기, 감지만 실행. 바꾼 값은 바로 저장되고 실행 중에도 반영됩니다.
- **Freebie**: 사용 여부, 수령 기준(초록 막대 높이), 확인 주기, 감지만 실행. 기본은 꺼져 있습니다.

처음에는 Lootbug 탭에서 **감지만 실행**을 켜고 돌려보세요. 탭은 하지 않고, 찾은 루트버그를 표시한 이미지를 `debug` 폴더에 저장합니다.

## 게임 설정 (Setup 탭)

버튼을 누르면 홈 하단 가운데 메뉴 버튼 → Options로 들어가 설정 탭(Gameplay / Menus / Display)을 차례로 열고, 목록을 맨 위로 올린 뒤 내려가며 항목을 찾아 다른 것만 바꾼 다음 홈 화면으로 돌아옵니다.

**필수 설정** (매크로 동작에 필요, `필수 설정 확인 및 적용`)

필수 설정을 확인해 모든 항목이 정상 또는 바꿈으로 끝나야 Run이 실행됩니다. 결과는 `config.json`에 기록되고 Setup 탭에 "확인됨 (날짜)"로 표시됩니다. 확인하지 않았거나 맞추지 못한 항목이 있으면 Run을 눌러도 실행하지 않고 로그로 안내합니다. 이후 버전에서 필수 항목이 늘어나면 다시 확인해야 합니다.

| 탭 › 묶음 | 항목 | 필요 |
|---|---|---|
| Gameplay › Bombs & Items | Disable Confirmation on Fire All Bombs | 체크 (폭탄 일괄 발사 기능용) |
| Gameplay › Lootbugs & Freebies | Auto-Loot free Lootbug offerings | 체크 |
| | Remove Lootbug Gem confirmation | 해제 |
| | Enable Loot-All Banked Lootbugs | 체크 |
| | Tap any Lootbug to Loot-All | 체크 |
| | One Click Claim all Banked Freebies | 체크 |

**추천 설정** (데미지 숫자와 효과를 줄여 화면 인식이 잘 되게 함, 묶음별 `적용` 또는 `추천 설정 전체 적용`)

| 탭 › 묶음 | 항목 | 추천 |
|---|---|---|
| Menus › Drones | Make Drones Invisible | 체크 |
| Menus › Stargazing | Make Stars Invisible | All of them (누를 때마다 단계가 바뀌어 이 문구가 나올 때까지 누름) |
| Display › Popups & Tooltips | Disable Ore Damage Popups, More Compact Text Popups, Hide Void Portal Resource Gain Popups, Hide Coal Full Popup | 체크 |
| Display › Graphics | Consistent Ore Position, Minimize Mining Effects To Stop Flashing, Disable All Bomb Animations, Cloud Zone Brightness Reduction, Disable Drone radius display | 체크 |

## 캡처와 메모리

LD플레이어는 `screencap`을 반복하면 메모리가 조금씩 늘고, LD플레이어를 다시 시작해야 돌아옵니다. 그래서 두 가지 캡처 방식을 둡니다.

| 방식 | 설정 | 동작 |
|---|---|---|
| 일반 캡처 | 기본 | 필요할 때마다 `screencap`. PNG 대신 압축하지 않은 형식으로 받아 해석 시간이 약 8ms → 1ms. 지원하지 않는 기기면 PNG로 자동 전환 |
| 연속 캡처(영상) | Options › 연속 캡처 | `screenrecord`로 H.264 영상을 계속 받아 가장 최근 장면을 씀 (`pip install av` 필요). 탭 뒤에는 0.25초 이후 장면만 씀. 영상이 끊기면 다시 연결하고, 세 번 연속 실패하면 일반 캡처로 진행 |

캡처가 실패하면 2, 5, 10, 20, 30초 간격으로 다시 시도하고 ADB도 다시 연결합니다. 탭은 다시 보내지 않습니다. 해상도가 720×1280이 아니면 다시 시도하지 않고 멈춥니다.

실행 중에는 1분마다 메모리를 재서 `logs/memory.jsonl`에 남기고 Status의 메모리 줄에 보여 줍니다 (`psutil` 필요).

| 값 (`config.json` › `general.memory`) | 기본 | 의미 |
|---|---|---|
| `interval_sec` | 60 | 측정 간격 |
| `ldplayer_warn_mb` | 4096 | LD플레이어 프로세스 합이 넘으면 경고 (10분에 한 번) |
| `warn_available_mb` | 1000 | 시스템 여유 메모리가 이보다 적으면 경고 |
| `stop_available_mb` | 500 | 이보다 적으면 매크로를 멈추고 LD플레이어 재시작을 안내 |

## 예외 상황

지금은 아래 상황을 `[!]` 로그로 남기고 정해진 대로 넘어갑니다.

| 기능 | 상황 | 처리 |
|---|---|---|
| Lootbug | 홈 화면이 아님 | 이번 주기 건너뜀 |
| Lootbug | 시작할 때 팝업이 이미 열려 있음 | 이어서 처리 |
| Lootbug | 탭했는데 팝업이 안 열림 | 바로 다시 찾음 (실패: 팝업) |
| Lootbug | 버프 아이콘을 판별 못 함 | 그 행은 체크 해제 |
| Lootbug | 체크박스가 반영 안 됨 | 2초 기다린 뒤 한 번 더, 그래도 안 되면 실패: 체크 |
| Lootbug | 행 목록이 읽을 때마다 다름 | 0.5초 간격으로 두 번 같게 읽힐 때까지 최대 4번 다시 읽음 |
| Lootbug | 중간 행이 가려져 안 보임 | 구매하지 않고 닫음 (실패: 보류) |
| Lootbug | 설정과 다른 체크가 남음 | 구매하지 않고 닫음 (실패: 보류) |
| Lootbug | 읽은 행에 체크가 없는데 Buy Checked가 켜져 있음 (못 본 행에 체크) | 구매하지 않고 닫음 (실패: 보류) |
| Lootbug | Buy Checked 후에도 버튼 활성 | 구매 안 된 것으로 셈 (실패: 구매) |
| Lootbug | X로 안 닫힘 | 최대 3번, `allow_back_key`가 켜져 있으면 뒤로가기 |
| 공통 | 홈 화면 복귀 확인 안 됨 | 다음 주기에 다시 확인 |
| Freebie | 시작할 때 메뉴가 열려 있음 | 상점 안에서 이어서 진행 |
| Freebie | 상점이 안 열림 / Pack 못 찾음 | 상점 닫고 다음 주기 |
| Freebie | 초록 막대는 있는데 Claim 비활성 | 상점 닫고 다음 주기 |
| Freebie | Banked 개수 못 읽음, '/' 옆 글자 중 하나라도 못 읽음, 개수가 0이거나 최대치보다 큼 | 숫자를 잘라 읽지 않고 개수 없이 Claim (실패: 개수) |
| Freebie | Banked 최대치가 이번 실행에서 앞서 읽은 값과 다름 | 그대로 받되 `[!]`로 남겨 화면 저장 |
| Freebie | Claim 후 버튼이 그대로 | 한 번 더, 그래도 안 되면 실패: Claim |
| Bombs | 가방 버튼을 못 찾음 / 열리지 않음 | 다음 주기 (실패: 가방) |
| Bombs | 윗줄 4칸이 예상한 폭탄이 아님 | 터뜨리지 않고 가방 닫음 (실패: 칸 확인) |
| Bombs | 칸이 선택되지 않음 | 한 번 더 누르고, 그래도 안 되면 그 폭탄만 건너뜀 (실패: 선택) |
| Bombs | Fire All로 바뀌지 않음 | 그 폭탄만 건너뜀 (실패: Fire All 전환) |
| Bombs | Fire All 뒤 남은 개수 표시가 그대로 | 충전이 없던 것으로 보고 다음 폭탄 |
| Bombs | 가방이 닫히지 않음 | 한 번 더, 그래도 안 되면 실패: 가방 안 닫힘 |
| Setup | 메뉴/Options/설정 탭 이동 실패, 항목 못 찾음, 바꾸지 못함 | 결과 칸에 표시하고 홈으로 복귀 시도 |
| 공통 | 캡처 실패 | 2/5/10/20/30초 간격으로 다시 시도, 그래도 안 되면 그 기능의 이번 주기만 건너뜀 |
| 공통 | 해상도가 540×960, 720×1280 둘 다 아님 | 실행 정지 |
| 공통 | ADB 오류 | 그 기능의 이번 주기만 건너뜀 |
| 공통 | 예상하지 못한 오류 | 그 기능의 이번 주기만 건너뜀. 같은 기능에서 5번 연속이면 실행 정지. 자세한 내용은 `logs/error.log` |
| 공통 | 시스템 여유 메모리 부족 | 실행 정지, LD플레이어 재시작 안내 |

## 로그 ID

로그마다 앞에 붙는 16진수 ID는 `연월일시분초(yyMMddHHmmss) + 그 초 안의 순번(01부터)`을 16진수로 바꾼 값입니다.

```
2026-11-02 20:49:35 첫 로그  → 26110220493501 → 17BF426AE2BD
같은 초 두 번째 로그        → 26110220493502 → 17BF426AE2BE
20:49:36 첫 로그            → 26110220493601 → 17BF426AE321
```

되돌릴 때는 `python -c "print(int('17BF426AE2BD', 16))"`.

## 루트버그 동작

1. 홈 화면에서 루트버그(7개 스킨 × 일반/황금)가 보이면 하나를 탭
2. 팝업 각 행의 버프 아이콘을 읽어 체크 상태를 설정과 같게 맞춤
   - 원하는 버프인데 체크가 없으면 체크, 원하지 않는데 체크돼 있으면 해제
   - 아이콘을 판별하지 못한 행은 젬 낭비를 막기 위해 체크 해제
   - 이미 산 행(0x, 회색)은 건드리지 않음
3. `Buy Checked`가 활성화돼 있으면 탭 (살 게 없으면 게임이 비활성화하므로 건너뜀)
4. 하단 X로 닫고 홈 화면 복귀 확인
5. 처리했으면 곧바로 다시 찾고(bank에 쌓인 루트버그), 없으면 확인 주기만큼 대기

## 프리비 동작

1. 홈 화면 오른쪽 아래 상점 버튼에 초록 막대가 기준 높이 이상 차오르면 상점 버튼을 탭
   (막대는 쌓인 비율 `N/최대`만큼 차오릅니다. 최대치는 계정마다 다르며, 5/35일 때 약 6px였습니다)
2. 상점을 아래로 스크롤하며 `Freebie Pack` 라벨을 찾고, 없으면 위로 스크롤하며 다시 찾음
3. Claim을 한 번 탭 (쌓인 프리비를 한꺼번에 받음). 버튼이 어두운 빨강(비활성)으로 바뀌면 완료, 안 바뀌면 한 번만 더 탭
4. 하단 X로 상점을 닫고 홈 화면 복귀 확인

## 폭탄 동작

Bombs 탭에서 켜고 순서를 고릅니다: `Cherry → Gem → Battery → D20` 또는 `Gem → Cherry → Battery → D20`.

1. 홈 화면 오른쪽 아래 폭탄 가방을 찾음. 스킨 8종(Default, Valentines, Easter, Magma, Summer, Halloween, Christmas, Baller)의 닫힘/열림 그림(위키)으로 판별
2. 닫혀 있으면 눌러 열고, 윗줄 왼쪽 4칸이 Gem, Cherry, Battery, D20인지 아이콘으로 확인 (다르면 터뜨리지 않음)
3. 순서대로 칸을 누르고 노란 테두리로 선택을 확인한 뒤, 발사 방식 버튼이 핵폭발(Fire All)인지 확인.
   토끼(Fire)나 거북(Fire Slow)이면 핵폭발이 나올 때까지 버튼을 누름. 그다음 Fire All
4. 칸의 남은 개수 표시가 바뀌면 발사로 셈. 바뀌지 않으면 충전이 없던 것으로 보고 다음 폭탄으로
5. 가방을 눌러 닫고 닫힘 확인

판별은 게임 원래 해상도(540×960) 픽셀로 합니다. Fire All 확인 창은 필수 게임 설정으로 꺼 둡니다.

## 구조

```
main.py                     실행 진입점
config.default.json         기본 설정 (사용자 설정은 config.json, git 제외)
assets/templates/
  lootbugs/                 루트버그 스킨 14장 ({skin}_{normal|golden}.png)
  buffs/                    버프 아이콘 견본: <키>.png는 위키 이미지(11종), <키>@game.png는 게임 화면에서 자른 것(9종)
  ui/                       루트버그 팝업 헤더, Freebie Pack 라벨, Options 아이콘, 설정 항목 라벨
  bombs/                    폭탄 가방 스킨 8종 닫힘/열림(bag/), 폭탄 칸 아이콘 4종, 발사 방식 아이콘 3종
  digits/                   게임 글자 0~9와 '/' 견본 (회색 테두리를 살린 이미지, 글자당 여러 장)
obelisk/
  core/                     ADB, 연속 캡처(stream), 메모리 감시(health), 이미지 처리, 홈 화면 판별, 실행 스레드
  features/                 기능별 코드 (lootbug, freebie, bombs)
  setup/                    게임 설정 확인 및 적용
  gui/                      통합 GUI (Home / Setup / Lootbug / Freebie / Bombs 탭)
```

새 기능은 `obelisk/features/`에 `Feature`를 상속한 클래스를 만들고 `features/__init__.py`의 `FEATURES`에 추가하면 실행기가 함께 돌립니다.

## exe 만들기 (PyInstaller)

```
pip install pyinstaller
pyinstaller --noconsole --name ObeliskMacro --add-data "assets;assets" --add-data "config.default.json;." main.py
```

`dist/ObeliskMacro` 폴더째로 배포합니다. `config.json`과 `debug` 폴더는 exe 옆에 생깁니다.
