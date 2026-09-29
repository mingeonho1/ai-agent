# 실행 환경

Claude Fable 5.1은 공식 모델 `claude-fable-5-1`이며 Opus 별칭이 아니다.
Fable 5.1은 Claude Code v2.1.257 이상이 필요하고, Opus 5.5(`claude-opus-5-5`)와
Sonnet 5.5(`claude-sonnet-5-5`)는 최신 Claude Code로 갱신한다(`claude update`).
별칭은 `opus`→Opus 5.5, `sonnet`→Sonnet 5.5, `fable`→Fable 5.1로 풀린다.
Bedrock·Vertex에서는 별칭이 다르게 풀리므로 전체 모델 ID를 사용한다.

```sh
claude --model claude-fable-5-1 --effort high
```

`CLAUDE_CODE_EFFORT_LEVEL`은 agent frontmatter의 effort보다 우선한다.
subagent 모델은 호출 시 지정 → frontmatter `model` → `CLAUDE_CODE_SUBAGENT_MODEL`
환경 변수 → 메인 대화 모델 순으로 결정된다. `/fast`(Fast mode)는 Opus 5.5에서 동작한다.
모델 강제 지정이나 조직의 모델·effort 제한도 실제 실행에 영향을 줄 수 있다.
요청한 설정과 다르면 이를 보고하고 사용자의 환경 변수를 임의로 변경하지 않는다.
이 패키지의 파일 검증은 계정별 모델 접근이나 실제 모델 실행의 증거가 아니다.

사용자 설치의 기본 구성 루트는 `~/.claude/`다. 비어 있지 않은
`CLAUDE_CONFIG_DIR`가 지정되면 그 경로를 구성 루트로 사용하고, 변수가 없거나
빈 문자열이면 기본 경로로 돌아간다. 사용자 agent는 구성 루트의 `agents/`에,
skill은 `skills/claude-agent-operations/`와 `skills/agent-evaluation-loop/`에
설치한다. 프로젝트 설치는 `.claude/agents/`와 `.claude/skills/`를 사용한다.
native Claude 구성에는 `agents/openai.yaml`이 필요하지 않다.

이 패키지의 `hooks/compact-reminder.json`은 선택 사항이다. 명시적으로 설치하면
`SessionStart`의 `compact` 이벤트에서 짧은 정적 알림만 context에 넣는다.
인수인계 파일을 탐색하거나 대화 기록을 읽지 않으며 승인이나 모델 호출을 하지 않는다.
기존 hooks를 덮어쓰지 않고 설치 도구가 해당 항목을 병합한다.

공식 근거:

- [모델과 effort 설정](https://code.claude.com/docs/en/model-config)
- [Subagent 파일과 독립 context](https://code.claude.com/docs/en/sub-agents)
- [Skill 설치 위치](https://code.claude.com/docs/en/skills)
- [SessionStart hook](https://code.claude.com/docs/en/hooks#sessionstart)
- [Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/overview)
- [Effort 가이드](https://platform.claude.com/docs/en/build-with-claude/effort)
- [베스트 프랙티스](https://code.claude.com/docs/en/best-practices)
