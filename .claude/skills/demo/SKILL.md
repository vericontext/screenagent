---
name: demo
description: screenagent 데모 시나리오를 실행하고 결과를 검증한다. Chrome 상태 확인, 에이전트 실행, 스크린샷 캡처, 결과 리포트까지 한번에 처리.
argument-hint: [scenario-description] [--model sonnet|haiku] [--max-steps N]
disable-model-invocation: true
---

# /demo Skill

screenagent 데모 시나리오를 한 커맨드로 실행하고 결과를 검증한다.

## Arguments

- 첫 번째 인자: 시나리오 설명 (예: "youtube.com에서 lofi 검색")
- `--model sonnet|haiku`: 사용할 모델 (기본: haiku)
- `--max-steps N`: 최대 스텝 수 (기본: 10)

## Procedure

### Step 1: Chrome 상태 확인

```bash
screenagent check --output json
```

- JSON 결과의 `ok` 필드를 확인한다.
- `ok: false`이면 사용자에게 Chrome 디버그 모드 실행을 안내하고 중단한다:
  ```
  Chrome CDP 연결 실패. 다음 명령어로 Chrome을 실행해주세요:
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug-profile
  ```

### Step 2: Chrome 초기화

CDP로 모든 탭을 닫고 about:blank 상태로 만든다:

```bash
# 현재 열린 탭 목록 확인
curl -s http://localhost:9222/json | python3 -c "
import sys, json
targets = json.load(sys.stdin)
pages = [t for t in targets if t.get('type') == 'page']
print(f'{len(pages)} tab(s) open')
for p in pages:
    print(f'  - {p.get(\"title\", \"untitled\")}: {p.get(\"url\", \"\")}')
"
```

열린 탭이 있으면 about:blank로 이동시킨다:

```bash
# 첫 번째 탭의 websocket URL을 가져와서 about:blank으로 navigate
curl -s http://localhost:9222/json | python3 -c "
import sys, json
targets = json.load(sys.stdin)
pages = [t for t in targets if t.get('type') == 'page']
if pages:
    # 첫 번째 탭만 남기고 나머지는 닫기
    for p in pages[1:]:
        import urllib.request
        urllib.request.urlopen(f'http://localhost:9222/json/close/{p[\"id\"]}', timeout=5)
    # 첫 번째 탭을 about:blank으로
    print(f'Reset to 1 tab: {pages[0][\"id\"]}')
"
```

### Step 3: 시나리오에서 모델과 max-steps 파싱

인자에서 `--model`과 `--max-steps` 값을 파싱한다.

- `--model sonnet` → `--model claude-sonnet-4-6`
- `--model haiku` → `--model claude-haiku-4-5-20251001` (기본값)
- `--max-steps N` → `--max-steps N` (기본값: 10)

나머지 텍스트가 시나리오 instruction이 된다.

### Step 4: screenagent 실행

```bash
screenagent run "<instruction>" --max-steps <N> --model <model> --output json 2>demo_stderr.log
```

- stderr 로그를 `demo_stderr.log`에 저장한다.
- 실행이 끝나면 stdout의 JSON 결과를 파싱한다.

### Step 5: 결과 스크린샷 캡처

```bash
screenagent screenshot --file demo_result.png --output json
```

- 캡처된 스크린샷을 Read 도구로 확인하여 사용자에게 보여준다.

### Step 6: 결과 리포트

다음 형식으로 결과를 정리한다:

```
## Demo Result

**시나리오**: <instruction>
**모델**: <model>
**스텝**: <사용된 스텝> / <max-steps>
**결과**: ✅ 성공 / ❌ 실패

### 에이전트 응답
<result summary>

### 스크린샷
[demo_result.png 표시]

### 로그 요약
<stderr 로그에서 주요 step 요약>
```

- 실패 시: 에러 내용을 분석하고, demo-debugger subagent 사용을 제안한다.
- 성공 시: 결과를 요약하고 스크린샷으로 확인한다.
