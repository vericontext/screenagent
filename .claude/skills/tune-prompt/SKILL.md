---
name: tune-prompt
description: screenagent의 시스템 프롬프트를 개선한다. 실패 로그를 분석해서 LLM이 더 정확하게 tool을 호출하도록 프롬프트를 수정.
argument-hint: [issue-description or log-path]
disable-model-invocation: true
---

# /tune-prompt Skill

screenagent의 시스템 프롬프트를 분석/개선하여 에이전트의 정확도를 높인다.

## 배경

현재 시스템 프롬프트: `src/screenagent/agent/loop.py`의 `SYSTEM_PROMPT`

에이전트 실패의 많은 원인이 프롬프트에서 비롯됨:
- LLM이 좌표를 잘못된 형식으로 반환 (이미 `_parse_coord`로 대응 중)
- 불필요한 탐색 스텝 (바로 할 수 있는 걸 돌아감)
- done을 너무 빨리/늦게 호출
- CDP 가용 여부 모르고 navigate 호출

## Procedure

### Step 1: 현재 프롬프트 분석

`src/screenagent/agent/loop.py`의 SYSTEM_PROMPT를 읽고 분석한다:
- 어떤 지침이 있는지
- 빠진 지침이 있는지
- 모호하거나 충돌하는 지침이 있는지

### Step 2: 실패 패턴 수집

인자로 이슈 설명이나 로그 경로가 주어지면 해당 내용을 분석한다.
없으면 일반적인 개선점을 제안한다.

일반적인 실패 패턴:

| 패턴 | 원인 | 프롬프트 개선 |
|------|------|---------------|
| 좌표 `"640, 197"` 형식 | LLM이 x,y를 하나로 묶음 | 좌표 형식 강조 (이미 있음) |
| 검색 후 Enter 안 누름 | 지시 부족 | "검색어 입력 후 Enter" 강조 |
| 같은 동작 반복 | 실패 감지 못함 | "이전 동작이 안 되면 다른 방법 시도" 추가 |
| 페이지 로딩 전 클릭 | 대기 부족 | "페이지 로드 후 스크린샷으로 확인" 추가 |
| done 너무 빨리 호출 | 완료 조건 모호 | "결과 화면을 스크린샷으로 확인 후 done" 추가 |
| 스크롤 안 함 | 화면 밖 요소 | "화면에 보이지 않으면 스크롤" 추가 |

### Step 3: 프롬프트 수정

`SYSTEM_PROMPT`를 수정한다. 원칙:
- **간결하게**: LLM은 긴 프롬프트보다 짧고 명확한 지침에 잘 반응
- **예시 포함**: 올바른 tool_call 예시를 넣으면 정확도 향상
- **우선순위**: 가장 자주 실패하는 패턴을 먼저 다룸
- **네거티브 예시**: "이렇게 하지 마" 보다 "이렇게 해" 가 효과적

### Step 4: tool 스키마 description도 함께 검토

`src/screenagent/agent/tools.py`의 각 tool description도 프롬프트의 일부.
모호한 description이 있으면 함께 수정한다.

### Step 5: 검증

```bash
# 테스트 통과
.venv/bin/python -m pytest tests/ -x -q

# dry-run으로 프롬프트 깨지지 않았는지 확인
.venv/bin/screenagent --output json run "test" --dry-run
```

가능하면 실제 시나리오로 테스트:
```bash
.venv/bin/screenagent run "<실패했던 시나리오>" --max-steps 5 2>tune_test.log
```

### Step 6: 결과 리포트

```
## Prompt Tuning Report

### 변경 사항
1. [변경 1 설명]
2. [변경 2 설명]

### 변경 전
​```
(이전 SYSTEM_PROMPT)
​```

### 변경 후
​```
(새 SYSTEM_PROMPT)
​```

### 기대 효과
- [실패 패턴 1]이 줄어들 것으로 예상
- [실패 패턴 2]에 대한 대응력 향상
```
