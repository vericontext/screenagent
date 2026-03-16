---
name: reset-chrome
description: Chrome의 모든 탭을 닫고 새 창을 열어 깨끗한 상태로 만든다
disable-model-invocation: true
---

# /reset-chrome Skill

Chrome 브라우저를 깨끗한 상태로 리셋한다.

## Procedure

### Step 1: CDP 연결 확인

```bash
screenagent check --output json
```

- `ok: false`이면:
  ```
  Chrome CDP 연결 실패. 다음 명령어로 Chrome을 실행해주세요:
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug-profile
  ```
  여기서 중단한다.

### Step 2: 현재 탭 상태 확인

```bash
curl -s http://localhost:9222/json | python3 -c "
import sys, json
targets = json.load(sys.stdin)
pages = [t for t in targets if t.get('type') == 'page']
print(f'{len(pages)} tab(s) open')
for p in pages:
    print(f'  - {p.get(\"title\", \"untitled\")}: {p.get(\"url\", \"\")}')
"
```

### Step 3: 탭 정리

모든 탭을 닫고 하나의 about:blank 탭만 남긴다:

```bash
curl -s http://localhost:9222/json | python3 -c "
import sys, json, urllib.request

targets = json.load(sys.stdin)
pages = [t for t in targets if t.get('type') == 'page']

if not pages:
    # 탭이 없으면 새 탭 생성
    urllib.request.urlopen('http://localhost:9222/json/new?about:blank', timeout=5)
    print('Created new blank tab')
else:
    # 첫 번째 탭 외 모두 닫기
    for p in pages[1:]:
        try:
            urllib.request.urlopen(f'http://localhost:9222/json/close/{p[\"id\"]}', timeout=5)
            print(f'Closed: {p.get(\"title\", \"untitled\")}')
        except Exception as e:
            print(f'Failed to close {p[\"id\"]}: {e}')

    # 남은 탭 수 확인
    print(f'Kept 1 tab: {pages[0].get(\"title\", \"untitled\")}')
"
```

첫 번째 탭을 about:blank으로 이동시킨다:

```bash
curl -s http://localhost:9222/json | python3 -c "
import sys, json, urllib.request
targets = json.load(sys.stdin)
pages = [t for t in targets if t.get('type') == 'page']
if pages:
    target_id = pages[0]['id']
    urllib.request.urlopen(f'http://localhost:9222/json/activate/{target_id}', timeout=5)
    print(f'Activated tab: {target_id}')
"
```

그 다음 about:blank으로 네비게이트한다:

```bash
screenagent run "주소창에 about:blank를 입력하고 엔터를 눌러줘" --max-steps 3 --dry-run
```

대신 CDP로 직접 navigate한다:

```bash
python3 -c "
import json, http.client

# Get first page target
conn = http.client.HTTPConnection('localhost', 9222)
conn.request('GET', '/json')
targets = json.loads(conn.getresponse().read())
pages = [t for t in targets if t.get('type') == 'page']

if pages:
    ws_url = pages[0].get('webSocketDebuggerUrl', '')
    target_id = pages[0]['id']
    # Use CDP HTTP endpoint to navigate
    conn.request('GET', f'/json/navigate/{target_id}?url=about:blank')
    print(conn.getresponse().read().decode())
    print('Navigated to about:blank')
conn.close()
"
```

### Step 4: 상태 확인

```bash
screenagent check --output json
```

결과를 보고한다:

```
Chrome 리셋 완료:
- 탭: 1개 (about:blank)
- CDP 연결: 정상
```
