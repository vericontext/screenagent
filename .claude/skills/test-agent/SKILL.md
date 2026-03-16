---
name: test-agent
description: screenagent CLI 도구들을 빠르게 검증한다. dry-run, screenshot, ax-tree, click 등 개별 기능을 테스트하고 결과를 리포트.
argument-hint: [tool-name or "all"]
disable-model-invocation: true
---

# /test-agent Skill

screenagent의 개별 CLI 도구들을 빠르게 테스트하고 결과를 리포트한다.

## Arguments

- `all`: 모든 도구를 순서대로 테스트
- 특정 도구 이름: `dry-run`, `screenshot`, `ax-tree`, `click`, `type`, `key`, `check`, `schema`

## Procedure

### 테스트 대상별 실행 방법

각 테스트는 `--output json`으로 실행하여 결과를 파싱한다.

#### 1. `dry-run` — 설정 검증

```bash
screenagent run "test" --dry-run --output json
```

- 확인: `ok` 필드가 `true`인지
- 확인: `config.api_key_set`이 `true`인지
- 확인: `config.model`이 유효한 모델명인지

#### 2. `screenshot` — 스크린샷 캡처

```bash
screenagent screenshot --file /tmp/test_screenshot.png --output json
```

- 확인: `path` 필드가 존재하는지
- 확인: `bytes`가 0보다 큰지
- 확인: 파일이 실제로 존재하는지

#### 3. `ax-tree` — 접근성 트리

```bash
screenagent ax-tree "Finder" --output json
```

- 확인: JSON 출력이 유효한지
- 확인: `role` 필드가 존재하는지
- 에러 시: 접근성 권한 문제인지 확인

#### 4. `click` — 마우스 클릭 (안전한 좌표 사용)

```bash
screenagent click 0 0 --output json
```

- 확인: `clicked` 필드가 존재하는지
- 주의: 화면 왼쪽 상단 구석(0,0)을 클릭하여 부작용 최소화

#### 5. `type` — 키보드 입력 (빈 앱 없이 테스트하므로 skip 가능)

이 테스트는 실제로 키 입력이 발생하므로, 현재 포커스된 앱에 텍스트가 입력될 수 있다.
`all`로 실행 시에는 이 테스트를 건너뛰고, 명시적으로 `type`을 지정했을 때만 실행한다.

```bash
screenagent type "test" --output json
```

- 확인: `typed` 필드가 `"test"`인지

#### 6. `key` — 키 입력

```bash
screenagent key escape --output json
```

- 확인: `pressed.key`가 `"escape"`인지
- Escape는 대부분의 상황에서 안전한 키이다.

#### 7. `check` — CDP 연결 확인

```bash
screenagent check --output json
```

- 확인: JSON 파싱 성공
- `ok: true`이면 CDP 정상, `ok: false`이면 CDP 미연결 (경고만, 실패 아님)

#### 8. `schema` — 도구 스키마

```bash
screenagent schema --output json
```

- 확인: `tools` 배열이 존재하는지
- 확인: 각 도구에 `name`, `description`, `input_schema`가 있는지

### 결과 리포트

모든 테스트 완료 후 다음 형식으로 보고한다:

```
## Test Report

| Tool       | Status | Details              |
|------------|--------|----------------------|
| dry-run    | ✅     | API key set, haiku   |
| screenshot | ✅     | 245KB captured       |
| ax-tree    | ✅     | Finder tree loaded   |
| click      | ✅     | (0, 0) clicked       |
| type       | ⏭️     | Skipped (all mode)   |
| key        | ✅     | escape pressed       |
| check      | ⚠️     | CDP not connected    |
| schema     | ✅     | 6 tools found        |

**Result**: 6/8 passed, 1 skipped, 1 warning
```

- ✅: 성공
- ❌: 실패 (에러 내용 포함)
- ⚠️: 경고 (기능은 동작하지만 주의 필요)
- ⏭️: 건너뜀
