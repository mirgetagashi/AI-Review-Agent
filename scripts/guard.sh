#!/usr/bin/env bash
# scripts/guard.sh - PreToolUse hook for the Bash tool.
#
# Replaces the denylist in section 7.2 of the design document. A denylist is
# the wrong shape for this job: the original pattern
#
#     grep -qE 'rm -rf|git push|curl .*\| *(ba)?sh|python .*work/|node .*work/'
#
# let all of these through, every one of which runs student code or destroys
# data:
#
#     python3 work/repo/main.py        # "python3 " is not "python "
#     cd work/repo && python main.py   # no "work/" after "python"
#     sh work/repo/run.sh
#     make run
#     ./main.py
#
# This version inverts the default: nothing runs unless it matches the
# allowlist, every segment of a compound command is vetted separately, and any
# failure to understand the input blocks instead of allowing.
#
# The command is tokenized the way bash reads it (quotes, escapes, redirections),
# and every path it names is resolved through symlinks from every directory the
# command may be in. Writes must land in work/, reports/ or /tmp; reads must stay
# inside the project or /tmp. A '..' component is refused outright.
#
# Contract: exit 0 allows, exit 2 blocks and returns the stderr text to the agent.
# The hook is defence in depth, NOT the security boundary - the boundary is
# scripts/sandbox-run.sh (no network, no privileges, resource limits).

set -o pipefail

LOG="${GUARD_LOG:-reports/guard.log}"

block() {
  local reason="$1" cmd="$2"
  if [[ -d "$(dirname "$LOG")" ]]; then
    printf '%s\tBLOCKED\t%s\t%s\n' "$(date -Is)" "$reason" "$cmd" >>"$LOG" 2>/dev/null || true
  fi
  echo "Blocked by scripts/guard.sh: ${reason}" >&2
  echo "Command: ${cmd}" >&2
  echo "Analysis commands must match the allowlist; student code runs only via 'bash scripts/sandbox-run.sh'." >&2
  exit 2
}

# ---------------------------------------------------------------------------
# Fail closed: anything that cannot be parsed is treated as hostile.
# ---------------------------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  echo "Blocked by scripts/guard.sh: jq is not installed, so commands cannot be inspected." >&2
  exit 2
fi

PAYLOAD="$(cat)"
if [[ -z "${PAYLOAD// }" ]]; then
  echo "Blocked by scripts/guard.sh: empty hook payload." >&2
  exit 2
fi

if ! TOOL="$(printf '%s' "$PAYLOAD" | jq -re '.tool_name // "Bash"' 2>/dev/null)"; then
  echo "Blocked by scripts/guard.sh: hook payload is not valid JSON." >&2
  exit 2
fi

# Non-Bash tools carry no shell command to vet.
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

CMD="$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.command // ""' 2>/dev/null)"
if [[ -z "${CMD// }" ]]; then
  echo "Blocked by scripts/guard.sh: Bash tool call with no command field." >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Where the command runs and which trees it may touch, all as physical paths.
# ---------------------------------------------------------------------------
physical_dir() { (cd -P -- "$1" 2>/dev/null && pwd -P); }

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT_P="$(physical_dir "$ROOT")" || block "project directory '${ROOT}' cannot be resolved" "$CMD"
TMP_P="$(physical_dir /tmp)" || TMP_P=/tmp

HOOK_CWD="$(printf '%s' "$PAYLOAD" | jq -r '.cwd // ""' 2>/dev/null)"
HOOK_CWD="$(physical_dir "${HOOK_CWD:-$PWD}")" || block "working directory cannot be resolved" "$CMD"

# resolve_path <base> <path>: the physical path, following every symlink that
# exists. A symlink as the last component is refused: it is the one way a
# student repository can point a read or a write at a file outside it.
resolve_path() {
  local p="$2" rest=""
  [[ "$p" == /* ]] || p="$1/$p"
  [[ "$p" == /* ]] || return 1
  while [[ ! -d "$p" ]]; do
    [[ -L "$p" ]] && return 1
    rest="/${p##*/}$rest"
    p="${p%/*}"
    [[ -z "$p" ]] && p=/
  done
  p="$(physical_dir "$p")" || return 1
  printf '%s%s' "${p%/}" "$rest"
}

WORK_P="$(resolve_path "$ROOT_P" work)" || block "work/ cannot be resolved" "$CMD"
REPORTS_P="$(resolve_path "$ROOT_P" reports)" || block "reports/ cannot be resolved" "$CMD"

# Every directory a later segment may run in. A 'cd' that fails leaves the
# shell where it was, so a path must be safe from all of them, not the last.
CWDS=("$HOOK_CWD")

in_tree() { [[ "$1" == "$2" || "$1" == "$2"/* ]]; }

# path_ok <path> <tree...>: true when <path>, resolved from every possible
# working directory, lies inside one of the trees.
path_ok() {
  local path="$1" base resolved tree
  shift
  [[ "$path" == /dev/null ]] && return 0
  [[ "/$path/" == */../* ]] && return 1
  for base in "${CWDS[@]}"; do
    resolved="$(resolve_path "$base" "$path")" || return 1
    for tree in "$@"; do
      in_tree "$resolved" "$tree" && continue 2
    done
    return 1
  done
  return 0
}

# An absolute path to the project's own scripts is the same script; without
# this the first real run blocked 'bash /Users/.../scripts/sandbox-run.sh'.
for prefix in "$ROOT/scripts/" "$ROOT_P/scripts/"; do
  while [[ "$CMD" == *"$prefix"* ]]; do
    CMD="${CMD%%"$prefix"*}scripts/${CMD#*"$prefix"}"
  done
done

# ---------------------------------------------------------------------------
# Hard denials, checked against the WHOLE command first: clearer messages, and
# they catch flags that turn an allowlisted binary into an execution primitive.
# Quotes and backslashes are removed first, so 'r""m' or '.co"nf"ig' match too.
# ---------------------------------------------------------------------------
DENY_TEXT="${CMD//[\"\'\\]/}"
DENY=(
  '\brm\b|\brmdir\b|\bmv\b|\bshred\b|\btruncate\b'
  '\bchmod\b|\bchown\b|\bchgrp\b'
  '\bsudo\b|\bsu\b|\bdoas\b'
  '\bdd\b|\bmkfs|\bfdisk\b'
  'git[[:space:]]+push'
  'git[[:space:]]+(reset|clean|checkout|restore|filter-branch|gc|am|apply)'
  'git[[:space:]]+(-c|--config)[[:space:]]'
  '--upload-pack|--receive-pack|--exec='
  '\bcurl\b|\bwget\b|\bnc\b|\bncat\b|\bssh\b|\bscp\b|\brsync\b|\bftp\b'
  '\bpip[23]?[[:space:]]+install|\bnpm[[:space:]]+(i|install)|\byarn[[:space:]]+add'
  '\bgem[[:space:]]+install|\bcargo[[:space:]]+install|\buv[[:space:]]+(pip|run)'
  '\bdocker\b|\bpodman\b'
  # find's execution, deletion and file-writing actions, anchored as whole flags:
  # unanchored, '-ok' also matched repository names such as 'john-oklahoma'.
  '(^|[[:space:]])-(exec|execdir|delete|ok|okdir|fprint|fprint0|fprintf|fls)([[:space:]]|$)'
  # flags that make an allowlisted reader run a program (--output is vetted per command below)
  '--pre(-glob)?([[:space:]=]|$)|--compress-program'
  # following symlinks while recursing would read whatever a student link targets
  '(^|[[:space:]])(-R|-L|-follow|--follow|--dereference-recursive)([[:space:]]|$)'
  # gh api is allowed below for GitHub metadata, read-only: these flags turn it
  # into a write (POST/PATCH/DELETE) or let it read a local file.
  'gh[[:space:]]+api.*[[:space:]](-X|--method|-f|-F|--field|--raw-field|--input)([[:space:]=]|$)'
  '--show-token'
  '\bawk\b|\bperl\b|\bruby\b|\bphp\b|\bmake\b|\bcmake\b'
  'sort[[:space:]][^|;]*-o[[:space:]]'
  '\bcrontab\b|\bsystemctl\b|\bservice\b|\bkill\b|\bpkill\b'
  # anchored to a command position: '--source' and '--install' are legitimate
  # flags of allowlisted tools, 'source' and 'install' as commands are not.
  '(^|[[:space:]])(eval|exec|source|env|export|unset|alias|history|install|tee|ln)([[:space:]]|$)'
  '/etc/|/proc/|/sys/|\.ssh|\.netrc|\.aws|_history|id_rsa|id_ed25519'
  '\.config/gh|hosts\.yml|\.git-credentials|\.npmrc|\.pypirc|\.docker/|\.kube/|\.gnupg'
  '(^|[/[:space:]=])\.env([.[:space:]]|$)'
)
for pattern in "${DENY[@]}"; do
  if [[ "$DENY_TEXT" =~ $pattern ]]; then
    block "matches denied pattern /${pattern}/" "$CMD"
  fi
done

# Command and process substitution hide a second command inside the first.
case "$CMD" in
  *'$('*|*'`'*|*'<('*|*'>('*) block "command or process substitution is not allowed" "$CMD" ;;
esac

# ---------------------------------------------------------------------------
# Allowlist, applied to EVERY segment of a compound command. This is what the
# original denylist missed: 'cd work/repo && python main.py' is two commands,
# and only the second one matters.
# ---------------------------------------------------------------------------
ALLOW=(
  # clone: https GitHub only
  '^git[[:space:]]+clone([[:space:]]+--[a-z-]+)*[[:space:]]+https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git)?([[:space:]]+(work|reports)/[A-Za-z0-9_./-]+)?$'
  # read-only git inspection, optionally with -C <path>
  '^git([[:space:]]+-C[[:space:]]+[A-Za-z0-9_./-]+)?[[:space:]]+(log|show|rev-parse|rev-list|diff|ls-files|ls-tree|shortlog|cat-file|status|branch|tag|describe|blame)([[:space:]].*)?$'
  '^git([[:space:]]+-C[[:space:]]+[A-Za-z0-9_./-]+)?[[:space:]]+config[[:space:]]+--get([[:space:]].*)?$'
  # analysis tools from section 6.6
  '^scc([[:space:]].*)?$'
  '^gitleaks[[:space:]]+detect([[:space:]].*)?$'
  '^ruff[[:space:]]+check([[:space:]].*)?$'
  '^jscpd([[:space:]].*)?$'
  '^gh[[:space:]]+search[[:space:]]+code([[:space:]].*)?$'
  # exactly this: any flag could print the token
  '^gh[[:space:]]+auth[[:space:]]+status$'
  # GitHub metadata, read-only (fork/parent/created_at, a file's contents):
  # 'repos/<owner>/<repo>[/path]', optional '--jq <expr-without-spaces>' and
  # '-H <header>'. Mutating flags are denied above.
  '^gh[[:space:]]+api[[:space:]]+repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/[A-Za-z0-9_./-]+)?([[:space:]]+(--jq|-q)[[:space:]]+[^[:space:]]+|[[:space:]]+(-H|--header)[[:space:]]+("[^"]*"|[^[:space:]]+))*$'
  # read-only inspection
  '^(find|grep|rg|wc|sort|uniq|head|tail|cat|ls|file|stat|basename|dirname|cut|tr|column|jq|cmp|diff|md5sum|sha256sum)([[:space:]].*)?$'
  # sed only as a line printer: 'sed -n 5p', '-e 6p -e 149p', '70,84p;108,200p'.
  # Any other script could write (w) or execute (e).
  '^sed[[:space:]]+-n(([[:space:]]+-e)?[[:space:]]+'"'"'?[0-9]+(,[0-9]+)?p(;[0-9]+(,[0-9]+)?p)*'"'"'?)+([[:space:]]+[A-Za-z0-9_./-]+)+$'
  '^check-jsonschema[[:space:]]+--schemafile[[:space:]]+[A-Za-z0-9_./-]+\.json([[:space:]]+[A-Za-z0-9_./-]+\.json)+$'
  '^cd[[:space:]]+(work|reports)/[A-Za-z0-9_./-]+$'
  '^mkdir[[:space:]]+-p[[:space:]]+(work|reports)/[A-Za-z0-9_./-]+$'
  '^echo([[:space:]].*)?$'
  # the only scripts allowed to run
  '^python3[[:space:]]+scripts/score\.py([[:space:]].*)?$'
  '^python3[[:space:]]+scripts/history_originality\.py([[:space:]].*)?$'
  '^bash[[:space:]]+scripts/sandbox-run\.sh([[:space:]].*)?$'
  '^true$'
)

is_allowed() {
  local segment="$1" pattern
  for pattern in "${ALLOW[@]}"; do
    [[ "$segment" =~ $pattern ]] && return 0
  done
  return 1
}

# ---------------------------------------------------------------------------
# Tokenizer. Splitting the raw text on ; & | blocked 'grep "a;b"' and jq filters
# with '|', and a regex over '>' let '>&CLAUDE.md' and 'work/../x' through.
# ---------------------------------------------------------------------------
S="$CMD"
N=${#S}
POS=0
WORD=""
RAW=""
WORD_ERR=""

# read_word: one shell word from POS, as bash would see it. WORD is its value
# (quotes and escapes removed), RAW the text as written. Fails on what the
# guard will not reason about: unbalanced quotes and every kind of expansion.
read_word() {
  local c q=""
  WORD=""
  RAW=""
  WORD_ERR=""
  while (( POS < N )); do
    c="${S:POS:1}"
    if [[ "$q" == "'" ]]; then
      [[ "$c" == "'" ]] && q="" || WORD+="$c"
    elif [[ "$q" == '"' ]]; then
      if [[ "$c" == '"' ]]; then
        q=""
      elif [[ "$c" == '$' ]]; then
        WORD_ERR="variable expansion is not allowed"; return 1
      elif [[ "$c" == '\' ]]; then
        RAW+="$c"; ((POS++)); c="${S:POS:1}"
        # inside double quotes a backslash escapes only these; elsewhere it is literal
        case "$c" in '$'|'`'|'"'|'\'|$'\n') WORD+="$c" ;; *) WORD+="\\$c" ;; esac
      else
        WORD+="$c"
      fi
    else
      case "$c" in
        [[:space:]]|';'|'&'|'|'|'<'|'>'|'('|')') break ;;
        "'"|'"') q="$c" ;;
        '$') WORD_ERR="variable expansion is not allowed"; return 1 ;;
        '{') WORD_ERR="brace expansion is not allowed"; return 1 ;;
        '~')
          if [[ -z "$WORD" || "$WORD" == *= || "$WORD" == *: ]]; then
            WORD_ERR="'~' expands to the home directory"; return 1
          fi
          WORD+="$c" ;;
        '\')
          RAW+="$c"; ((POS++)); c="${S:POS:1}"
          [[ "$c" != $'\n' ]] && WORD+="$c" ;;
        *) WORD+="$c" ;;
      esac
    fi
    RAW+="$c"
    ((POS++))
  done
  if [[ -n "$q" ]]; then
    WORD_ERR="unbalanced quotes"; return 1
  fi
  return 0
}

SEG_WORDS=()
SEG_RAWS=()
SEG_WRITES=()
SEG_READS=()

# vet_segment: checks the segment collected so far, then starts a new one.
vet_segment() {
  local words=("${SEG_WORDS[@]}") raws=("${SEG_RAWS[@]}") writes=("${SEG_WRITES[@]}") reads=("${SEG_READS[@]}")
  local text="" i w value target base resolved
  SEG_WORDS=(); SEG_RAWS=(); SEG_WRITES=(); SEG_READS=()

  for target in "${writes[@]}"; do
    path_ok "$target" "$WORK_P" "$REPORTS_P" "$TMP_P" \
      || block "write outside reports/, work/ or /tmp, through '..' or through a symlink: '${target}'" "$CMD"
  done
  for target in "${reads[@]}"; do
    path_ok "$target" "$ROOT_P" "$TMP_P" || block "input redirection from outside the project: '${target}'" "$CMD"
  done
  (( ${#words[@]} == 0 )) && return 0

  # leading VAR=value assignments: only the one the clone step needs
  while (( ${#words[@]} > 0 )) && [[ "${words[0]}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; do
    [[ "${words[0]}" == "GIT_TERMINAL_PROMPT=0" ]] || block "environment assignment '${words[0]}' is not allowed" "$CMD"
    words=("${words[@]:1}")
    raws=("${raws[@]:1}")
  done
  (( ${#words[@]} == 0 )) && return 0

  for w in "${raws[@]}"; do
    text+="${text:+ }$w"
  done
  is_allowed "$text" || block "command not on the allowlist: '${text}'" "$CMD"

  # every argument that could be a path must stay inside the project or /tmp
  for (( i = 1; i < ${#words[@]}; i++ )); do
    w="${words[i]}"
    case "$w" in
      --*=*) value="${w#*=}" ;;
      -*) continue ;;
      *) value="$w" ;;
    esac
    path_ok "$value" "$ROOT_P" "$TMP_P" || block "path outside the project, through '..' or through a symlink: '${value}'" "$CMD"
  done

  # arguments that are written to or executed in
  case "${words[0]}" in
    cd)
      path_ok "${words[1]}" "$WORK_P" "$REPORTS_P" || block "cd outside work/ or reports/: '${words[1]}'" "$CMD"
      for base in "${CWDS[@]}"; do
        resolved="$(resolve_path "$base" "${words[1]}")" && CWDS+=("$resolved")
      done ;;
    mkdir)
      path_ok "${words[2]}" "$WORK_P" "$REPORTS_P" || block "mkdir outside work/ or reports/: '${words[2]}'" "$CMD" ;;
    git)
      if [[ "${words[1]}" == clone && "${words[${#words[@]}-1]}" != https://* ]]; then
        target="${words[${#words[@]}-1]}"
        path_ok "$target" "$WORK_P" "$REPORTS_P" || block "clone outside work/ or reports/: '${target}'" "$CMD"
      fi ;;
    bash)
      path_ok "${words[2]}" "$WORK_P" || block "the sandbox runs only directories inside work/: '${words[2]}'" "$CMD" ;;
  esac
  for (( i = 1; i < ${#words[@]}; i++ )); do
    case "${words[i]}" in
      --out|--out-dir) target="${words[i+1]}" ;;
      --out=*|--out-dir=*) target="${words[i]#*=}" ;;
      # only jscpd may choose where its report goes; git diff/log --output writes any file
      --output|--output=*)
        [[ "${words[0]}" == jscpd ]] || block "--output writes a file: '${text}'" "$CMD"
        [[ "${words[i]}" == --output=* ]] && target="${words[i]#*=}" || target="${words[i+1]}" ;;
      -o)
        [[ "${words[0]}" == jscpd ]] || continue
        target="${words[i+1]}" ;;
      *) continue ;;
    esac
    path_ok "$target" "$WORK_P" "$REPORTS_P" || block "output outside work/ or reports/: '${target}'" "$CMD"
  done
  return 0
}

# redirection: called with POS on '<' or '>'.
redirection() {
  local mode
  if [[ "${S:POS:1}" == '>' ]]; then
    ((POS++))
    case "${S:POS:1}" in
      '>'|'|') ((POS++)); mode=write ;;
      '&') ((POS++)); mode=dup ;;
      *) mode=write ;;
    esac
  else
    ((POS++))
    case "${S:POS:1}" in
      '<')
        ((POS++))
        [[ "${S:POS:1}" == '<' ]] || block "here-documents are not allowed" "$CMD"
        ((POS++)); mode=herestring ;;
      '>') ((POS++)); mode=write ;;
      '&') ((POS++)); mode=dup ;;
      *) mode=read ;;
    esac
  fi
  while [[ "${S:POS:1}" == [[:blank:]] ]]; do ((POS++)); done
  read_word || block "$WORD_ERR" "$CMD"
  [[ -z "$RAW" ]] && block "redirection without a target" "$CMD"
  case "$mode" in
    write) SEG_WRITES+=("$WORD") ;;
    read) SEG_READS+=("$WORD") ;;
    # '>&2' duplicates a descriptor; '>&file' is a plain write to file
    dup) [[ "$WORD" =~ ^([0-9]+-?|-)$ ]] || SEG_WRITES+=("$WORD") ;;
  esac
}

while :; do
  while [[ "${S:POS:1}" == [[:blank:]] ]]; do ((POS++)); done
  if (( POS >= N )); then
    vet_segment
    break
  fi
  case "${S:POS:1}" in
    ';'|$'\n')
      vet_segment; ((POS++)) ;;
    '|')
      vet_segment; ((POS++))
      [[ "${S:POS:1}" == '|' || "${S:POS:1}" == '&' ]] && ((POS++)) ;;
    '&')
      if [[ "${S:POS+1:1}" == '>' ]]; then
        # &> and &>> write both streams to a file
        ((POS++))
        redirection
      else
        vet_segment; ((POS++))
        [[ "${S:POS:1}" == '&' ]] && ((POS++))
      fi ;;
    '<'|'>')
      redirection ;;
    '('|')')
      block "subshells are not allowed" "$CMD" ;;
    *)
      read_word || block "$WORD_ERR" "$CMD"
      # a descriptor number glued to a redirection ('2>/dev/null') is not an argument
      if [[ "$RAW" =~ ^[0-9]+$ && "${S:POS:1}" == [\<\>] ]]; then
        continue
      fi
      SEG_WORDS+=("$WORD")
      SEG_RAWS+=("$RAW") ;;
  esac
done

exit 0
