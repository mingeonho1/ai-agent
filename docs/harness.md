# 필요한 하네스만 남긴 이유

공식 문서 확인일: 2026-09-29. 모델 역할과 추론값은 사용자가 지정한 운영 설정이다. 아래는 그 설정을 구현하면서 참고한 공식 문서와 실제 적용 범위다. 문서에 등장한다는 이유만으로 전부 추가하지 않았다.

## Claude Code

| 공식 자료·부분 | 적용 |
| --- | --- |
| [Models overview](https://platform.claude.com/docs/en/models/overview), 모델 ID | Fable 5.1 `claude-fable-5-1`, Opus 5.5 `claude-opus-5-5`, Sonnet 5.5 `claude-sonnet-5-5`를 구분(Opus 5·Sonnet 5는 legacy) |
| [Effort](https://platform.claude.com/docs/en/build-with-claude/effort), 지원 수준 | 기획 high, 빌더·실행 medium, 검증 xhigh. 공식 권장(Fable 기본 high, Sonnet 5.5 에이전틱 medium 시작, Opus 5.5 기본 medium)에 맞춘 선택이며 최고 추론을 전체 단계에 일괄 적용하지 않음 |
| [Model configuration](https://code.claude.com/docs/en/model-config), effort 우선순위 | 전역 환경변수가 역할별 설정을 덮어쓰는 경우를 설치 설명에 명시 |
| [Subagents](https://code.claude.com/docs/en/sub-agents), custom subagents | 역할을 Markdown 파일로 등록. 검증자는 새 컨텍스트에서 시작하고 Read/Grep/Glob만 제공. frontmatter의 `effort`로 세션 effort를 덮어쓰고 `skills`로 루브릭·체크리스트를 프리로드 |
| [Skills](https://code.claude.com/docs/en/skills), skill 위치 | Claude 전용 `.claude/skills`에 설치. 메인 Skill이 역할을 조율 |
| [Settings](https://code.claude.com/docs/en/settings#find-or-create-your-settings-files), 사용자 설정 경로 | `CLAUDE_CONFIG_DIR`가 있으면 해당 폴더에 사용자 등록 |
| [Hooks](https://code.claude.com/docs/en/hooks), 이벤트와 실행 형식 | Stop·PostCompact·SubagentStop 등 이벤트와 command·prompt·agent 타입 훅이 있지만, 이 저장소는 SessionStart `compact` 안내만 제공하고 매 도구 호출 훅·자동 모델 리뷰 루프는 추가하지 않음 |
| [Best practices](https://code.claude.com/docs/en/best-practices), 루프 종료 게이트 | 프롬프트 내 검사·`/goal`·Stop 훅·검증 서브에이전트 4종 중 검증 서브에이전트를 핵심으로 삼고 나머지는 선택 옵션으로 둠 |

Anthropic의 [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)에서 **구현자와 평가자 분리**, **관찰 가능한 완료 기준**, **파일을 통한 인수인계**를 가져왔다. 이 글은 2026-03-24의 실험이므로 당시 모델별 결과를 Fable 5.1의 측정 결과처럼 쓰지 않았다. 여러 차례 디자인 점수를 올리는 반복 실험도 이 저장소의 기본값으로 가져오지 않았다.

2026-04-08의 [Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents)는 모델이 발전하면 예전 보정 장치가 불필요해질 수 있다고 설명한다. 따라서 일정 토큰마다 세션을 강제로 초기화하는 장치는 두지 않는다. **독립 평가와 레드팀의 컨텍스트를 분리**하고, 긴 작업은 작은 인수인계 문서로 이어 간다.

[Fable 5.1 프롬프팅 가이드](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1)에서 빌더·검토 지시문에 세 가지를 반영했다. 전체를 다시 쓰기보다 필요한 부분만 수정한다, 작업 중 발견한 범위 밖 문제는 고치지 않고 후속으로 보고한다, 턴을 끝내기 전 남은 미완 작업은 지금 수행한다. 아울러 [일반 프롬프팅 베스트 프랙티스](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)에 따라 "반드시·항상·CRITICAL" 같은 강조 어조를 평서문으로 낮춰 과잉 트리거를 줄였다. 독립성·소유권·안전 규칙은 그대로 뒀다.

## Codex

| 공식 자료·부분 | 적용 |
| --- | --- |
| [모델 목록](https://developers.openai.com/api/docs/models), 모델 ID | Astra / Sol / Luna를 서로 다른 역할로 고정 |
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra), reasoning 지원 | 기획 high → 검증 xhigh로 한 단계 상승 |
| [Subagents](https://learn.chatgpt.com/codex/agent-configuration/subagents), Custom agents | `name`, `description`, `developer_instructions`가 있는 독립 TOML과 역할별 추론값, `[agents] max_concurrent_threads_per_session`로 동시성 제한 |
| [Build skills](https://learn.chatgpt.com/codex/build-skills), 로컬 검색 경로 | Skill은 `.agents/skills`, 에이전트는 `.codex/agents`에 분리 설치 |
| [Hooks](https://learn.chatgpt.com/codex/hooks), 이벤트와 실행 형식 | 훅은 존재하며 command·mcp_tool만 실행한다. 이 저장소는 기본 훅을 추가하지 않고 Claude 설정을 그대로 복사하지 않음 |
| [Config reference](https://learn.chatgpt.com/codex/config-file/config-reference), `review_model`·프로필 | `review_model`로 `/review` 모델을 지정하고, 프로필은 `~/.codex/<name>.config.toml` + `--profile` 파일 방식(0.134.0 이후) |

2026-09-11의 [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) 중 **Better skills**, **Up-to-date AGENTS.md**, **Persistence**를 반영했다. Astra에는 읽을 문서와 수행 단계를 전부 나열하지 않고, 판단할 쟁점과 완료 기준을 전달한다. Skill 설명은 짧게 하고 상세 계약은 필요할 때 읽는다. Sol 빌더에게는 수정 파일·입출력·검증 명령을 구체적으로 준다. Luna는 정해진 탐색과 명령 실행만 맡는다.

검증 완료를 위해 필요한 검사는 끝까지 수행하되, 통과한 뒤 같은 테스트와 리뷰를 이유 없이 반복하지 않는다. 이는 [Astra 모델 가이드](https://developers.openai.com/api/docs/guides/latest-model)의 **Subagent delegation / Testing and verification**도 함께 참고했다.

## 공통 운영 선택

1. 요청을 작업 ID와 관찰 가능한 완료 기준으로 남긴다. 인수인계는 해당 작업의 경로를 명시한다.
2. 독립 조사나 쓰는 파일이 다른 구현만 병렬로 보낸다. 기본 동시 작업자는 3명 이내다. 이 숫자는 플랫폼 제한이 아닌 이 저장소의 선택이다.
3. 검증자는 사용자 요구사항·안정된 diff·현재 파일·실행 증거를 읽는다. 전체 대화와 빌더의 설득 문장을 넘기지 않는다.
4. 추가 정보가 필요하면 특정 파일이나 검사를 요청한다. 컨텍스트 분리는 필요한 근거를 숨기는 것이 아니다.
5. 검증 모델을 사용할 수 없으면 그 사실을 보고한다. 자기 검토를 독립 검증으로 대체하지 않는다.

Skill은 모델에게 주는 실행 규칙이고 역할 파일은 런타임의 모델·추론 설정이다. 훅을 포함하더라도 리뷰가 수행됐는지를 외부에서 강제하는 시스템은 아니다. 설치만으로 실제 모델 호출까지 검증됐다고 주장하지 않는다.

평가 기록과 반복 개선은 [평가 루프](evaluation.md), 기획·코드의 반례 탐색은 [레드팀](../red-team/README.md)에 별도로 정리했다. 점수 계산과 반복 상한은 스크립트로 검사하지만, 근거의 진위와 실제 독립 실행 여부는 리뷰어·오케스트레이터가 확인해야 한다.
