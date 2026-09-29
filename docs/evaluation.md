# 점수를 개선 기록으로 쓰는 방법

공식 문서 확인일: 2026-09-29. 이 저장소의 평가는 결과물의 약점을 찾기 위한 운영 도구다. 모델의 일반 성능이나 토큰 절감률을 입증하는 벤치마크가 아니다.

## 공식 자료에서 가져온 것

| 자료·해당 부분 | 적용 |
| --- | --- |
| [OpenAI Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices), Design your eval process / LLM-as-a-judge | 작업별 기준을 먼저 정의하고 관찰 가능한 점수 예시를 둔다. 사람이 판정한 예시로 보정하고, 점수와 통과 조건을 함께 사용한다. |
| [OpenAI Graders](https://developers.openai.com/api/docs/guides/graders), Grader hacking | 모델의 판단과 결정적 계산을 나눈다. 점수를 올리려고 검사·기준을 약화한 경우 개선으로 인정하지 않는다. |
| [OpenAI Trace grading](https://developers.openai.com/api/docs/guides/trace-grading), structured scores and labels | 실패한 단계·검사·증거 경로를 기록해 수정 대상을 찾는다. API나 전체 대화 기록 수집을 도입한 것은 아니다. |
| [OpenAI 독립 평가 지침](https://openai.com/index/trustworthy-third-party-evaluations-foundations/), 2026-05-29, harness / validity / reporting | 어떤 주장을 시험했는지, 모델·추론·도구·예산을 기록한다. 잘못된 문제·평가 우회·비교 조건 변경을 확인한다. |
| [Anthropic Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), 2026-01-09 | 에이전트의 완료 선언보다 실제 결과를 확인한다. 결정적 검사와 판단이 필요한 평가를 조합하고 실패 사례를 회귀 검사로 남긴다. |
| [Anthropic Harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps), 2026-03-24, evaluator / iteration | 구현과 평가를 분리한다. 평가 예시와 차원별 문턱을 두고 반복 결과를 비교한다. 논문의 실험 횟수나 성능 수치는 가져오지 않았다. |
| [OpenAI Evals 종료 공지](https://developers.openai.com/api/docs/deprecations) | Evals 대시보드·API는 2026-10-31 읽기 전용, 2026-11-30 종료 예정이다. 이 저장소는 그 API를 호출하지 않고 방법론만 참고하며, 후속 도구는 [Datasets](https://developers.openai.com/api/docs/guides/evaluation-getting-started)다. |
| [OpenAI Agent evals](https://developers.openai.com/api/docs/guides/agent-evals) | 에이전트 실행의 최종 상태·궤적을 확인하는 관점을 참고한다. 이 저장소의 루프는 로컬 스크립트로 집계하고 이 API를 호출하지 않는다. |

## 플랫폼에 맞춘 적용

Claude는 Markdown named subagent의 `model`, `effort`, `tools`를 사용한다. 평가자는 새 Fable 5.1 xhigh, 기록과 개선 제안은 Opus 5.5 medium이다. 기존의 선택형 `SessionStart` 훅 외에 매 호출 평가 훅을 추가하지 않는다.

Codex는 TOML 역할 설정을 사용한다. 새 Astra xhigh가 고정된 기준으로 평가하고, Sol medium이 기록과 다음 수정 범위를 다룬다. 실행 증거 확보는 Luna high에 맡길 수 있다. 루프 제어를 위한 별도 런타임 훅은 두지 않는다.

두 플랫폼 모두 루프 에이전트가 직접 다른 에이전트를 만들지 않는다. 메인이 파일 소유권을 유지하면서 수정·재평가를 호출한다. 점수 계산 스크립트는 네트워크나 모델을 호출하지 않는다. 따라서 스크립트 실행만으로 실제 모델 리뷰가 수행됐다고 볼 수 없다.

## 반복 중에도 지킬 기준

- 기준과 배점은 작업 시작 전에 고정한다. 요구사항이 바뀌면 새 평가 버전을 만들고 이전 점수와 직접 비교하지 않는다.
- 재평가는 새 컨텍스트에서 원래 요구사항과 현재 증거를 읽는다. 이전 점수와 PASS 결론을 먼저 보여주지 않는다.
- 총점으로 필수 검사 실패나 확인된 중대한 결함을 상쇄하지 않는다. 증거 부족은 별도 상태로 남긴다.
- 모델의 설명이 길어졌거나 점수가 올랐다는 이유만으로 개선이라고 기록하지 않는다. 어떤 실패가 해결됐는지 확인한다.
- 통과하면 종료한다. 최초 평가를 포함해 3회, 연속 정체 2회라는 기본 한도에 도달하면 남은 문제를 보고한다. 한도 도달은 성공이 아니다.
- 모델·추론·기준 버전·산출물 식별자·실행 증거를 남긴다. 토큰·비용·시간을 측정하지 않았다면 `null`로 둔다. 비공개 사고 과정은 수집하지 않는다.
- 검증된 실패의 교훈은 프로젝트의 `evals/lessons/` 또는 계약에 지정한 경로에 보존한다. 다음 작업의 기획·루프 담당자가 적용 조건과 유효 상태를 확인해 새 검사에 반영하고, 리뷰어에게는 현재 기준과 증거만 전달한다.

배점, 통과선, 반복 한도, 이전 점수 비공개는 이 저장소의 운영 선택이다. 공식 문서의 강제 설정이 아니다. 예제 기록은 형식을 보여주는 가상 자료이며 실제 품질 향상이나 모델 실행 결과로 제시하지 않는다.
