# 근거와 적용 범위

확인 기준일: 2026-09-29. 아래는 유지되는 공식·1차 출처에서 가져온 검토 기법이다. 이 스킬은 해당 프레임워크를 설치하지 않으며, 공식 스킬이나 공식 승인을 받은 구현도 아니다.

## Anthropic: 에이전트 평가

- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), 2026-01-09: 말로 한 완료 주장보다 최종 상태를 확인하고, 모델 채점은 사람 판단과 보정하며, 회귀 평가와 채점 우회를 함께 살핀다. 이 스킬은 그래서 실제 결과·테스트 증거와 반증 가능한 기준을 요구한다.
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps), 2026-03-24: 구현자와 평가자 역할 분리, 구체적인 루브릭 기준, 비용이 큰 반복을 제한하는 설계를 참고했다. 글의 반복 횟수와 예산은 사례의 기본값이지 이 스킬의 의무가 아니다.

## Inspect Petri와 Bloom

- [Inspect Petri](https://github.com/meridianlabs-ai/inspect_petri)는 auditor·target·judge를 분리하고 일관된 루브릭으로 기록을 채점한다. [결과 문서](https://meridianlabs-ai.github.io/inspect_petri/using/results.html)는 판단 근거를 구체적 메시지에 연결하고, 감사 자체가 실패한 경우 표적 결론으로 오인하지 말라고 안내한다.
- Petri는 `safety-research/petri`에서 [meridianlabs-ai/inspect_petri](https://github.com/meridianlabs-ai/inspect_petri)로 이전됐다. [변경 기록](https://github.com/meridianlabs-ai/inspect_petri/blob/main/CHANGELOG.md)의 현재 릴리스는 3.1.0, 2026-07-22이다.
- Petri의 입증 범위는 AI 행동 감사다. 일반 코드·제품 설계 리뷰의 성능을 입증한 자료로 취급하지 않는다. 이 스킬은 역할 격리와 증거 연결이라는 기법만 참고한다.
- [Bloom 저장소](https://github.com/safety-research/bloom)와 [Anthropic 소개](https://www.anthropic.com/research/bloom), 2025-12-19: 동일 행동을 현실적이고 다양한 시나리오로 바꿔 평가하는 발상을 반례 설계에 적용한다. 2026년에 새로 나온 도구라고 부르지 않는다.

## 위험도와 평가 보고

- [OWASP Risk Rating Methodology](https://community.owasp.org/OWASP_Risk_Rating_Methodology): 위험을 발생 가능성과 영향으로 나누고 조직의 사업 맥락에 맞추라는 원칙을 참고했다. 이 스킬의 상·중·하 정의는 자체 3단계 영향 분류이며 OWASP의 공식 통일 척도가 아니다.
- [OpenAI: A shared playbook for trustworthy third party evaluations](https://openai.com/index/trustworthy-third-party-evaluations-foundations/), 2026-05-29: 검증하려는 주장을 명확히 하고 모델·하네스·도구·예산을 보고하며, 보상 해킹과 잘못된 정답·모호한 기준·누락 파일 같은 깨진 평가 조건을 점검한다.
- [OpenAI: Red teaming](https://developers.openai.com/api/docs/guides/red-teaming): evals는 시스템이 의도대로 동작하는지, red teaming은 적대적·예상 밖 입력에서 어떻게 동작하는지를 본다는 구분을 인용한다. 이 스킬은 Promptfoo 같은 도구를 설치하지 않고 역할 분리와 반례 설계 관점만 참고한다.

인기, 별점, 시장 지위는 측정 자료가 없으면 주장하지 않는다. 출처에서 직접 입증되지 않은 일반화는 이 스킬의 설계 선택이라고 밝힌다.
