# 두 계정 분담 (dual-account)

메인 계정은 Claude 앱(또는 CLI)에서 기획·판단·결과 종합에만 쓰고, 토큰을 많이 쓰는 실행은 서브 계정 CLI가 헤드리스로 처리한다. 메인 세션에는 지시문과 최종 보고만 남는다.

```
메인 (앱, 계정 A) ── 지시문 ──▶ alt-agent ──▶ 서브 CLI (계정 B, ~/.claude-alt)
        ▲                                         │ 구현·테스트·조사
        └────────────── 최종 보고 + 세션 ID ◀──────┘
```

## 구성

| 파일 | 역할 |
|---|---|
| [`setup.sh`](setup.sh) | `~/.claude-alt` 프로필 생성, 공유 항목 심링크, `alt-agent` 설치, 셸에 `claude2` 추가 |
| [`bin/alt-agent`](bin/alt-agent) | 서브 계정으로 `claude -p --agent <역할>` 실행, 결과만 출력 |

공유하는 것: `CLAUDE.md`, `settings.json`, `agents/`, `skills/`, `commands/`, `plugins/`, `projects/`(세션·메모리), 입력 히스토리. 공유하지 않는 것: 로그인(`.claude.json`, 키체인 항목은 설정 폴더별로 따로 저장된다), 세션 런타임 상태. 사용자 범위 MCP 서버 설정은 처음 한 번 복사한다.

## 설치

```bash
bash dual-account/setup.sh --dry-run
bash dual-account/setup.sh
```

새 셸에서 `claude2`를 실행하고 `/login`으로 서브 계정에 로그인한다. 두 프로필의 로그인은 `claude auth status`와 `CLAUDE_CONFIG_DIR=~/.claude-alt claude auth status`로 각각 확인한다.

## 사용

작업 레포로 이동한 뒤 실행한다. 메인 세션에서는 Bash 도구로 백그라운드 실행하면 끝날 때 결과만 돌아온다.

```bash
alt-agent ai-builder <<'EOF'
목표, 대상 파일, 완료 기준, 보고 형식을 자기완결적으로 쓴다.
EOF
```

- 전체 기록은 `~/.claude-alt/runs/`에 남는다. 자세한 과정은 `claude2 --resume <세션 ID>`로 본다.
- 종료코드 2는 서브 계정 미로그인·사용 한도·실행 실패다. 메인은 같은 지시문을 기본 서브에이전트로 넘긴다.
- 헤드리스 실행은 권한을 물을 수 없어 `--dangerously-skip-permissions`로 돈다. 신뢰하는 레포에서만 쓰고, 필요하면 워크트리에서 실행한다.
- 서브 실행에서는 훅을 끄고 MCP를 로드하지 않는다. 메인에 걸린 게이트·알림 훅이 두 번 돌지 않게 하려는 선택이다.

## 메인 지침에 넣을 문단

메인 세션이 위임 경로를 알도록 `~/.claude/CLAUDE.md`에 추가한다.

```markdown
## 서브 계정 위임 (메인 계정 토큰 절약)

메인 계정은 기획·판단·결과 종합에만 쓰고, 토큰을 많이 쓰는 작업은 서브 계정으로 보낸다.

- 다중 파일 구현·테스트·디버깅·긴 조사 → Bash 로 `~/.claude/bin/alt-agent ai-builder <<'EOF' … EOF`
  (작업 레포로 cd 후 백그라운드 실행). 계획·판단 충돌은 `ai-planner`, 단순 실행은 `ai-runner`.
- 지시문은 컨텍스트를 공유하지 않으므로 목표·대상 파일·완료 기준·보고 형식을 자기완결적으로 쓴다.
- 1~2개 파일 소규모 수정·단순 조회는 위임 비용이 더 크니 메인이 직접 한다.
- 종료코드 2면 같은 지시문으로 기본 서브에이전트에 위임하고 한 줄로 알린다.
- 같은 파일을 건드리는 alt-agent 를 동시에 두 개 돌리지 않는다.
```

## 주의

- `scripts/install.py --user`는 `CLAUDE_CONFIG_DIR`이 비어 있는 일반 셸에서 실행한다. `~/.claude-alt`의 `agents/`는 심링크라 설치 경로 검사에 걸리고, `~/.claude`에 설치하면 서브 계정에도 그대로 보인다.
- 같은 세션을 두 계정에서 동시에 이어 쓰지 않는다. 같은 기록 파일에 동시에 쓰면 꼬일 수 있다.
- 회사 계정과 개인 계정을 섞으면 회사 코드가 다른 계정에서 처리된다. 조직 정책을 먼저 확인한다.
- 사용 한도를 우회하려고 계정을 늘리는 용도라면 이용약관을 확인한다.
- 토큰 절감 효과는 아직 측정하지 않았다.
