---
name: agent-evaluation-loop
description: 구현 품질을 반복 평가하거나 근거 기반 개선 중단 조건이 필요할 때 사용한다. 독립 리뷰 점수표를 고정 루브릭으로 검증·집계하고 최대 3회의 개선 기록을 관리한다.
---

# Agent Evaluation Loop

메인 오케스트레이터가 이 스킬을 사용한다. 빌더와 독립 리뷰어는 기존 역할로 실행하고, `ai-loop`는 리뷰 점수표를 기록해 다음 한 가지 수정 또는 증거 보강 작업만 제안한다. `ai-loop`는 하위 agent를 호출하거나 소스를 수정하거나 점수를 만들지 않는다.

## 순서

1. 새 baseline 전에 플래너 또는 `ai-loop`가 프로젝트의 현재 교훈 중 이번 범위·조건에 맞는 항목을 읽고 현재 작업의 필수 기준으로 변환한다. 그 뒤 원래 요구사항, 필수 기준, [rubric.md](references/rubric.md)의 차원·가중치·앵커·통과 기준을 고정한다. 변경하려면 새 `evaluation_id`와 1회차 baseline으로 다시 시작한다.
2. 빌더가 후보를 만들고 검증 증거를 고정한 뒤, 최고 등급의 독립 리뷰어를 상속 없는 새 context에서 실행한다. 리뷰어에게 원래 요구사항, 필수 기준, 고정 루브릭·체크리스트의 실제 파일 경로, 현재 후보와 증거만 주며 이전 점수와 반복 기록은 보여주지 않는다.
3. 리뷰어는 차원별 `0..4` 또는 `null`, 근거, 필수 기준 결과, 발견 사항을 반환한다. 루브릭이나 필수 기준 판단에 꼭 필요한 증거가 없을 때만 finding을 `needs_evidence`로 표시한다. 선택적 가설이나 추가 탐색 아이디어는 이 상태로 넣지 않는다. 모르는 점수는 `null`로 두고 `NEEDS_EVIDENCE`로 처리한다.
4. `ai-loop`가 입력 JSON을 만들고 아래 도구로 검증·집계·추가 기록한다. 도구는 LLM이나 네트워크를 호출하지 않는다.

```sh
python3 <agent-evaluation-loop-dir>/scripts/evaluate.py --input round.json --history evaluation-history.jsonl
```

5. PASS가 아니면 기록의 `decision`과 `fix_targets`에서 근거가 있는 한 가지 수정 또는 증거 보강만 선택한다. 숫자를 올리기 위한 재시도, 통과 기준 완화, 테스트 제거를 금지한다.
6. baseline을 포함해 최대 3회만 평가한다. 결함 해결이나 새 증거가 없는 회차가 2회 연속이면 즉시 `STOP_NOT_COMPLETE`로 종료한다. 한도를 소진해도 통과하지 못하면 완료로 보고하지 않는다.
7. 독립 리뷰로 확인되고 수정된 결함은 최소 재현 입력과 기대 결과를 회귀 테스트 또는 평가 사례로 승격하고 아래 프로젝트 교훈에도 남긴다. 현재 작업 범위를 넘으면 후속 항목으로 기록하며, 같은 평가의 고정 루브릭을 바꾸지는 않는다.

## 프로젝트 교훈

기본 경로는 프로젝트의 `evals/lessons/`이며 작업 계약에서 다른 프로젝트 내부 경로를 정할 수 있다. 교훈은 [lesson.template.md](templates/lesson.template.md) 형식으로 다음 사실만 기록한다.

- 적용 범위와 발생 조건
- 검증된 실패와 증거
- 수정 원칙
- 최소 재현 절차와 기대 결과
- `current` 또는 `superseded` 상태와 유효 조건

점수, 승인 과정, 대화, 비공개 사고 과정은 기록하지 않는다. 교훈은 해당 작업·프로젝트 안에서만 유지하며 전역 개인 메모리로 복사하지 않는다. 새 baseline에서는 관련된 `current` 교훈만 골라 현재 필수 검사로 바꾼다. 새 독립 리뷰어에게는 현재 요구사항, 이렇게 만든 고정 검사, 현재 후보와 증거만 전달하며 교훈 기록 자체나 과거 점수·반복 이력은 전달하지 않는다.

## 통과와 기록

기본 PASS는 총점 85 이상, 모든 알려진 차원 3 이상, 모든 필수 기준 통과, 미해결 high·medium 발견 없음, 리뷰 격리와 모델 라우팅 확인을 모두 요구한다. 총점이 높아도 필수 기준 실패나 미해결 high·medium 발견은 통과를 막는다.

각 JSONL 기록에는 작업·후보·증거 fingerprint, 루브릭 버전, 실제 모델과 effort, 근거, 원점수, 결정, 수정 목표, 측정된 token·실행 시간·비용을 남긴다. 측정하지 않은 값은 `null`을 쓴다. 비공개 사고 과정은 수집하지 않는다. 같은 평가의 같은 회차는 덮어쓰지 않고 거부한다.

입력 구조는 [round-input.template.json](templates/round-input.template.json), 리뷰 출력 형식은 [reviewer-scorecard.md](templates/reviewer-scorecard.md)를 사용한다. [synthetic-baseline.json](examples/synthetic-baseline.json)은 동작 설명용 합성 예시이며 측정 결과가 아니다.
