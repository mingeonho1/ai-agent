---
name: claude-agent-operations
description: Claude Code에서 계획, 구현, 명령 실행, 독립 검토를 나누어 조율한다. 사용자가 이 역할 구성을 요청하거나 독립 작업의 병렬 위임이 필요한 작업에 사용한다.
---

# Claude Agent Operations

이 skill은 메인 대화에서 실행한다. 메인은 작업 계약, 파일 소유권, 결과 종합을
관리하고 아래 이름의 custom agent를 명시해 위임한다.

| 역할 | Agent | 모델 | Effort |
| --- | --- | --- | --- |
| 계획과 판단 | ai-planner | Claude Fable 5.1 (`claude-fable-5-1`) | high |
| 구현과 수정 | ai-builder | Claude Opus 5.5 (`claude-opus-5-5`) | medium |
| 조회와 명령 | ai-runner | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | medium |
| 독립 검토 | ai-reviewer | Claude Fable 5.1 (`claude-fable-5-1`) | xhigh |
| 평가 기록과 다음 행동 | ai-loop | Claude Opus 5.5 (`claude-opus-5-5`) | medium |

메인도 Fable 5.1 high로 운영하려면 해당 모델과 effort로 세션을 시작한다.
agent의 `model`과 `effort`는 설치된 정의에 따른다. agent가 없거나 지정 모델을
실행할 수 없으면 해당 단계를 멈추고 원인을 보고한다. 일반 agent나 다른 모델로
대체하지 않으며 실행하지 않은 검토를 통과한 것으로 처리하지 않는다.
환경 변수와 버전 확인이 필요하면 [runtime-support.md](references/runtime-support.md)를 읽는다.

## 진행

1. 목표, 완료 조건, 입력 경로, 소유 파일을 정한다. 최초 위임과 작업 재개 때
   [task-contract.md](references/task-contract.md)의 계약과 인수인계 형식을 사용한다.
2. 판단이 필요한 부분만 ai-planner에 보낸다. 단순 작업에는 별도 계획 호출을
   추가하지 않는다. 메인이 계약을 확정하고 의존 순서를 정한다.
3. ai-builder에는 수정 책임을, ai-runner에는 명령과 출력 책임을 준다.
   독립 작업만 병렬로 실행하며 동시에 실행하는 worker는 최대 3개로 한다.
   파일마다 작성자는 한 명이다. agent의 재위임은 사용하지 않는다.
   이 동시 실행 수와 재위임 금지는 이 harness의 운영 규칙이다.
4. worker는 핵심 결과, 증거 경로와 미해결 항목만 1~2k 토큰 이내 요약으로 반환한다.
   메인은 계약과 인수인계를 갱신한다. 긴 로그와 전체 대화 기록을 다음 agent에 넘기지 않는다.
5. 구현과 관련 검증이 끝나고 작성자가 모두 멈춘 뒤 현재 변경 목록과 diff를
   확정한다. Git이 없으면 변경 전후 파일과 변경 경로를 제공한다. ai-runner가
   diff와 명령 결과를 지정된 증거 파일에 저장할 수 있다.
6. **ai-reviewer를 항상 새 인스턴스로 실행한다.** 이전 reviewer를 재개하거나
   대화 기록을 상속하는 `fork` 타입을 쓰지 않는다. 요구사항, 확정된 diff,
   현재 파일 경로와 테스트 증거만 전달한다. builder의 설명과 사고 과정은 제외한다.
7. REJECT이면 ai-builder가 지적된 범위만 수정하고 관련 검증을 다시 수행한다.
   NEEDS_EVIDENCE이면 필요한 증거를 확보한다. 두 경우 모두 파일을 안정시킨 뒤
   새 reviewer에게 검토를 맡긴다. 같은 실패가 반복되면 무한 재시도하지 말고
   미해결 원인과 필요한 결정을 보고한다.
8. 최신 변경 상태에 대한 PASS와 완료 조건을 확인한 뒤 산출물, 검증 결과,
   남은 제한을 보고한다. 검토 후 파일이 바뀌면 해당 검토는 완료 근거로 쓰지 않는다.

## 평가 기반 개선

반복 평가가 필요한 작업은 설치된 `$agent-evaluation-loop`를 함께 사용한다.
이 방식은 공식 루프 종료 게이트 네 가지(프롬프트 내 검사, `/goal`, Stop 훅,
검증 서브에이전트) 중 "검증 서브에이전트"에 해당하며, 일한 에이전트가 스스로
채점하지 않도록 새 reviewer가 판정한다. `/goal`과 Stop 훅은 선택 옵션이다
(출처: https://code.claude.com/docs/en/best-practices).
구현 전에 원래 요구사항, 필수 기준, 차원·가중치·앵커·통과 기준을 고정한다.
각 회차마다 ai-reviewer를 상속 없는 새 인스턴스로 실행하며 원래 요구사항과 고정
루브릭·체크리스트의 실제 파일 경로는 주되 이전 점수와 반복 기록은 보여주지 않는다. reviewer의 구조화된
점수표만 ai-loop에 전달해 결정론적으로 집계·기록하고, ai-loop는 근거가 있는
다음 수정 또는 증거 보강 한 가지만 제안한다. ai-loop는 agent를 호출하거나
소스를 수정하거나 점수를 만들지 않는다.

baseline 포함 최대 3회이며, 결함 해결이나 새 증거가 없는 회차가 2번 연속이면
`STOP_NOT_COMPLETE`로 멈춘다. 숫자를 올리기 위한 재시도, 통과 기준 완화, 테스트
제거를 허용하지 않는다. 루브릭 변경은 새 버전과 새 baseline으로 시작한다.

읽기 전용 reviewer에는 Bash, Edit, Write, Agent를 제공하지 않는다. reviewer는
독립성을 위해 skills나 memory를 프리로드하지 않는다.
동일 checkout의 변경을 검토하므로 자동 worktree 생성은 필요하지 않다.
기존 사용자 규칙과 허가 범위는 유지하며 이 skill 자체가 push, PR, 외부 전송을
허가하지 않는다.
