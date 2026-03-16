---
name: perf-audit
description: screenagent 에이전트 루프의 성능 병목을 분석하고 코드를 개선한다. 스텝별 시간 측정, 불필요한 스크린샷 제거, sleep 최적화 등.
argument-hint: [run-log-path or "analyze"]
disable-model-invocation: true
---

# /perf-audit Skill

screenagent 에이전트 루프의 성능 병목을 찾아내고 코드를 개선한다.

## 배경

현재 에이전트 루프의 알려진 병목:
- 매 tool dispatch마다 스크린샷 캡처 (불필요할 수 있음)
- `asyncio.sleep()` 고정 대기 시간 (0.3s, 2s 등)
- LLM API 호출 대기 (줄일 수 없지만 토큰 수 줄이기 가능)
- 스크린샷 리사이즈 (`sips` 호출)

## Procedure

### Step 1: 현재 성능 측정

먼저 에이전트 루프를 dry-run이 아닌 실제 실행으로 시간을 측정한다.
인자로 로그 파일 경로가 주어지면 해당 로그를 분석한다.

로그가 없으면 `loop.py`의 `arun()` 메서드를 읽고 각 단계별 예상 시간을 계산한다:

```
src/screenagent/agent/loop.py 의 arun() 분석:
```

각 스텝에서 소요되는 시간 요소:
1. `_perceive_async()` — AX tree + CDP DOM + screenshot
2. `_client.messages.create()` — LLM API 호출
3. `_dispatch_tool()` — tool 실행 + sleep + 후속 screenshot
4. 메시지 직렬화/역직렬화

### Step 2: 병목 식별

`loop.py`와 `composite.py`를 읽고 다음을 체크한다:

#### 2a. 불필요한 스크린샷
- `_dispatch_tool`에서 click, type_text, key_press, scroll 후 모두 screenshot를 찍고 있음
- 연속 동작(click → type → enter)에서 중간 스크린샷은 불필요할 수 있음
- **개선**: tool 결과에 screenshot를 넣되, LLM이 다음 tool을 연속 호출할 때는 마지막 것만 사용

#### 2b. sleep 최적화
현재 sleep 값들:
- `_open_url_via_keyboard`: 0.3s + 0.1s + 0.3s + 2.0s = **2.7s** (URL 열 때마다)
- `click`: 0.3s
- `type_text`: 0.3s
- `key_press`: 0.3s
- `scroll`: 0.3s
- `navigate` (CDP): 1.0s

**개선 방안**:
- 페이지 로드 대기를 고정 sleep 대신 CDP `Page.loadEventFired` 이벤트 대기로 변경
- 클릭/타이핑 후 sleep을 0.1s로 줄여볼 수 있음

#### 2c. 이미지 크기 최적화
- 스크린샷이 클수록 LLM 토큰 소모 많고 API 응답 느림
- 현재 MAX_IMAGE_BYTES = 3.5MB → 너무 큼
- **개선**: 1MB 이하로 줄이면 API 응답 속도 향상

#### 2d. 히스토리 관리
- MAX_HISTORY = 10이지만 각 메시지에 이미지가 포함됨
- 오래된 메시지의 이미지를 제거하면 토큰 절약

### Step 3: 코드 수정 적용

분석 결과에 따라 실제 코드를 수정한다. 수정 대상 파일:

| 파일 | 개선 내용 |
|------|-----------|
| `src/screenagent/agent/loop.py` | sleep 값 조정, 히스토리 이미지 제거, 스텝 타이밍 로그 |
| `src/screenagent/perception/screenshot.py` | MAX_IMAGE_BYTES 축소 |
| `src/screenagent/perception/composite.py` | CDP 우선 screenshot, 불필요한 AX tree 스킵 |

수정 시 각 변경에 대해:
1. 변경 전 동작을 설명
2. 변경 후 기대 효과를 설명
3. 위험 요소가 있으면 명시

### Step 4: 검증

```bash
# 테스트 통과 확인
.venv/bin/python -m pytest tests/ -x -q

# dry-run 정상 확인
.venv/bin/screenagent --output json run "test" --dry-run
```

### Step 5: 결과 리포트

```
## Performance Audit Report

### 측정 결과
| 구간 | 변경 전 | 변경 후 | 절감 |
|------|---------|---------|------|
| URL 열기 | 2.7s | 0.8s | -70% |
| 클릭 후 대기 | 0.3s | 0.15s | -50% |
| 스크린샷 크기 | ~600KB | ~200KB | -67% |
| 스텝당 히스토리 토큰 | ~8K | ~4K | -50% |

### 적용된 변경
- [파일별 변경 내용]

### 추가 권장
- [더 할 수 있는 최적화]
```
