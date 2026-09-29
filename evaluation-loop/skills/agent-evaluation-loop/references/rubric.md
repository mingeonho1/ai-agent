# 기본 평가 루브릭

이 루브릭은 이 저장소의 미보정 기본값이며 공식 표준이 아니다. 소유자가 판정한 pass/fail 예시와 grader 결과가 일치하는지 확인하기 전에는 잠정값으로 취급하고 보정 통계를 추정하지 않는다. 작업을 시작하기 전에 요구사항에 맞게 필수 기준을 추가할 수 있지만, baseline 이후에는 같은 `evaluation_id`의 차원, 가중치, 앵커와 통과 기준을 바꾸지 않는다. 변경이 필요하면 루브릭 버전을 올리고 새 baseline을 만든다.

| 차원 | 가중치 | 0 | 1 | 2 | 3 | 4 |
| --- | ---: | --- | --- | --- | --- | --- |
| 의도 충족 (`intent`) | 30 | 요청과 무관 | 핵심 요구 대부분 누락 | 일부 충족, 중요한 누락 | 요구 충족, 작은 한계 | 요구와 경계를 완전 충족 |
| 정확성 (`correctness`) | 30 | 동작 불가·치명 결함 | 주요 경로 실패 | 부분 동작·중요 결함 | 주요 경로 정확, 작은 위험 | 경계 조건까지 근거로 확인 |
| 검증 (`verification`) | 20 | 검증 없음 | 관련성 낮거나 실패 은폐 | 핵심 경로 일부만 확인 | 관련 검증 통과, 한계 명시 | 실패 경로·회귀까지 충분히 확인 |
| 명료성 (`clarity`) | 10 | 이해·검토 불가 | 구조와 설명이 혼란 | 추가 해석이 필요 | 변경과 근거가 명확 | 간결하고 추적 가능하며 모호함 없음 |
| 효율 (`efficiency`) | 10 | 불필요한 비용·범위가 지배 | 큰 중복·과잉 | 일부 중복·과잉 | 범위와 비용이 적절 | 최소 범위로 재사용 가능하게 해결 |

점수는 각 `score / 4 * weight`를 합산한다. 한 차원이라도 증거가 불충분하면 점수를 추정하지 않고 `null`로 두며 총점도 `null`이다.

## 기본 게이트

- 총점 85 이상
- 모든 차원 3 이상
- 모든 필수 기준이 `true`
- 미해결 `high` 또는 `medium` 발견 없음
- 필수 모델·effort와 실제 리뷰 모델·effort 일치
- 상속 없는 새 리뷰 context 확인

재현 가능한 치명·high 결함과 필수 기준 실패는 총점과 무관하게 PASS를 막는다. 루브릭이나 테스트를 약화해 통과시키지 않는다. 모델 판정은 명확한 앵커와 근거를 요구하고, 결정론적 검사는 별도로 결합한다. 사람 기준과 보정하지 않은 점수는 절대 품질 수치로 주장하지 않는다.

## 근거

- [OpenAI Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices): 명확한 루브릭과 앵커, pass/fail 게이트, 강한 judge, 사람 판정과의 보정, 위치·장황성 편향
- [OpenAI Graders](https://developers.openai.com/api/docs/guides/graders): 결정론적 grader와 모델 grader의 결합, 보상 해킹 점검
- [Trustworthy third-party evaluations](https://openai.com/index/trustworthy-third-party-evaluations-foundations/): 모델·하니스·예산 기록, 주장 자체의 검증, 깨진 기준과 보상 해킹 방지
- [Anthropic, Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents): 결과 근거, 명확한 가중·이진·혼합 채점, grader 보정, 회귀 사례
- [Anthropic, Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps): 점수 앵커 예시, 구현과 평가 역할 분리, 반복 개선
- OpenAI Evals 대시보드·API는 2026-10-31 읽기 전용, 2026-11-30 종료 예정([공지](https://developers.openai.com/api/docs/deprecations))이다. 이 루프는 그 API를 호출하지 않고 방법론만 참고하며, 후속 도구는 [Datasets](https://developers.openai.com/api/docs/guides/evaluation-getting-started)다.
