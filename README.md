# idle-obelisk-macro

LD플레이어에서 실행하는 Idle Obelisk Miner 자동 수령 매크로입니다. ADB로 화면을 캡처하고 OpenCV로 인식해서 탭하므로, 게임 창이 다른 창에 가려져 있어도 동작합니다.

| 기능 | 상태 |
|---|---|
| Lootbug: 루트버그 탭, 설정한 버프만 체크해서 Buy Checked, 팝업 닫기 | 사용 가능 |
| Freebie: 상점 버튼의 초록 막대 확인, 상점 스크롤로 Freebie Pack 찾기, Claim, 상점 닫기 | 사용 가능 |

## 준비

1. LD플레이어 설정
   - 해상도: 휴대폰 **720×1280** (세로). 다른 해상도면 시작할 때 오류가 납니다.
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
  오른쪽의 **Debug**를 켜면 로그 한 줄마다 그 순간 화면을 `debug/로그ID.png`로 저장하고, `debug/debug.log`에 ID와 로그를 남깁니다.
- **Setup**: 매크로에 필요한 게임 설정을 확인하고 맞춥니다 (아래 참고). 매크로 실행 중에는 쓸 수 없습니다.
- **Lootbug**: 사용 여부, 구매할 버프, 확인 주기, 감지만 실행. 바꾼 값은 바로 저장되고 실행 중에도 반영됩니다.
- **Freebie**: 사용 여부, 수령 기준(초록 막대 높이), 확인 주기, 감지만 실행. 기본은 꺼져 있습니다.

처음에는 Lootbug 탭에서 **감지만 실행**을 켜고 돌려보세요. 탭은 하지 않고, 찾은 루트버그를 표시한 이미지를 `debug` 폴더에 저장합니다.

## 게임 설정 (Setup 탭)

게임 Options → Gameplay → Lootbugs & Freebies가 아래와 같아야 매크로가 동작합니다.

| 항목 | 필요 |
|---|---|
| Auto-Loot free Lootbug offerings | 체크 |
| Remove Lootbug Gem confirmation | 해제 |
| Enable Loot-All Banked Lootbugs | 체크 |
| Tap any Lootbug to Loot-All | 체크 |
| One Click Claim all Banked Freebies | 체크 |

Setup 탭의 버튼을 누르면 홈 하단 가운데 메뉴 버튼 → Options → Gameplay 탭으로 이동해 각 항목을 확인하고, 다른 항목은 체크박스를 눌러 맞춘 뒤 홈 화면으로 돌아옵니다.

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
   (막대 높이는 쌓인 프리비 수에 비례하며, Banked 5/35일 때 약 6px)
2. 상점을 아래로 스크롤하며 `Freebie Pack` 라벨을 찾고, 없으면 위로 스크롤하며 다시 찾음
3. Claim을 한 번 탭 (쌓인 프리비를 한꺼번에 받음). 버튼이 어두운 빨강(비활성)으로 바뀌면 완료, 안 바뀌면 한 번만 더 탭
4. 하단 X로 상점을 닫고 홈 화면 복귀 확인

## 구조

```
main.py                     실행 진입점
config.default.json         기본 설정 (사용자 설정은 config.json, git 제외)
assets/templates/
  lootbugs/                 루트버그 스킨 14장 ({skin}_{normal|golden}.png)
  buffs/                    버프 아이콘 11장 (위키 이미지)
  ui/                       루트버그 팝업 헤더, Freebie Pack 라벨, Options 아이콘, 설정 항목 라벨
obelisk/
  core/                     ADB, 이미지 처리, 홈 화면 판별, 실행 스레드
  features/                 기능별 코드 (lootbug, freebie)
  setup/                    게임 설정 확인 및 적용
  gui/                      통합 GUI (Home / Setup / Lootbug / Freebie 탭)
```

새 기능은 `obelisk/features/`에 `Feature`를 상속한 클래스를 만들고 `features/__init__.py`의 `FEATURES`에 추가하면 실행기가 함께 돌립니다.

## exe 만들기 (PyInstaller)

```
pip install pyinstaller
pyinstaller --noconsole --name ObeliskMacro --add-data "assets;assets" --add-data "config.default.json;." main.py
```

`dist/ObeliskMacro` 폴더째로 배포합니다. `config.json`과 `debug` 폴더는 exe 옆에 생깁니다.
