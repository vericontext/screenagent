---
name: add-tool
description: screenagent에 새로운 tool을 추가한다. 스키마 정의, dispatch 구현, CLI 연동, 테스트까지 한번에 처리.
argument-hint: <tool-name> <description>
disable-model-invocation: true
---

# /add-tool Skill

screenagent 에이전트에 새 tool을 추가하는 전체 과정을 자동화한다.

## Arguments

- `tool-name`: 추가할 도구 이름 (snake_case, 예: `wait_for_element`, `extract_text`)
- `description`: 도구 설명

## 수정 대상 파일

새 tool을 추가하려면 반드시 다음 파일들을 수정해야 한다:

1. **`src/screenagent/agent/tools.py`** — 도구 스키마 정의 (TOOLS 리스트에 추가)
2. **`src/screenagent/agent/loop.py`** — `_dispatch_tool()` 메서드에 핸들러 추가
3. **`src/screenagent/cli.py`** — (선택) CLI 서브커맨드로도 노출할 경우
4. **`tests/test_cli.py`** — 테스트 추가

## Procedure

### Step 1: 기존 도구 패턴 파악

먼저 현재 도구 목록을 확인한다:

```bash
.venv/bin/screenagent --output json schema | python3 -c "
import sys, json
tools = json.load(sys.stdin)['tools']
for t in tools:
    print(f\"  {t['name']}: {t['description'][:60]}\")
"
```

### Step 2: 스키마 정의

`src/screenagent/agent/tools.py`의 TOOLS 리스트에 새 도구 스키마를 추가한다.

기존 패턴을 따라:
```python
{
    "name": "<tool-name>",
    "description": "<description>",
    "input_schema": {
        "type": "object",
        "properties": {
            # ... 파라미터 정의
        },
        "required": [...]
    }
}
```

### Step 3: dispatch 구현

`src/screenagent/agent/loop.py`의 `_dispatch_tool()` 메서드에 elif 블록을 추가한다.

패턴:
```python
elif name == "<tool-name>":
    # 구현
    return ToolResult(output="...", screenshot_png=png)
```

도구 유형별 구현 가이드:
- **인식(perception) 도구**: `self._perceiver`를 통해 정보 수집 → ToolResult(output=...)
- **행동(action) 도구**: `self._actor` 또는 `self._cdp_actor`를 통해 실행 → 후속 screenshot
- **CDP 전용 도구**: `await self._get_cdp_actor()`로 CDP 사용 가능 여부 먼저 확인
- **순수 정보 도구**: 외부 상태 변경 없이 정보만 반환

### Step 4: 시스템 프롬프트 업데이트

새 도구의 사용법이 비직관적이면 `loop.py`의 `SYSTEM_PROMPT`에 가이드를 추가한다.

### Step 5: CLI 서브커맨드 (선택)

사용자가 CLI에서 직접 호출할 수 있게 하려면 `cli.py`에:
1. `cmd_<tool_name>` 함수 추가
2. `build_parser()`에 서브커맨드 추가
3. `dispatch` 딕셔너리에 등록

### Step 6: 테스트

```bash
# 스키마 확인
.venv/bin/screenagent --output json schema | python3 -c "
import sys, json
tools = json.load(sys.stdin)['tools']
names = [t['name'] for t in tools]
assert '<tool-name>' in names, f'Tool not found! Got: {names}'
print('Schema OK')
"

# 기존 테스트 통과 확인
.venv/bin/python -m pytest tests/ -x -q
```

### Step 7: 결과 리포트

```
## Tool Added: <tool-name>

**설명**: <description>
**파라미터**: <params>

### 수정된 파일
- `tools.py` — 스키마 추가
- `loop.py` — dispatch 핸들러 추가
- `cli.py` — (선택) 서브커맨드 추가

### 테스트
- 스키마: ✅
- 기존 테스트: ✅
```
