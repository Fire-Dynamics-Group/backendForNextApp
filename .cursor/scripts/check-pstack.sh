#!/usr/bin/env bash
# Red/green pin for vendored pstack. Fail unless:
#   1. .cursor/skills/poteto-mode/SKILL.md exists
#   2. .cursor/settings.json is valid JSON with plugins.pstack.enabled true
#   3. .cursor/rules/pstack-models.mdc exists, and every active model setting
#      is grok-4.6 (comments may mention other ids, e.g. the 8 Nov 2026 switch)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILL="$ROOT/.cursor/skills/poteto-mode/SKILL.md"
SETTINGS="$ROOT/.cursor/settings.json"
MODELS="$ROOT/.cursor/rules/pstack-models.mdc"
fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -f "$SKILL" ]] || fail "missing $SKILL"
[[ -f "$SETTINGS" ]] || fail "missing $SETTINGS"
[[ -f "$MODELS" ]] || fail "missing $MODELS"

python3 - "$SETTINGS" "$MODELS" <<'PY'
import json, re, sys

settings_path, models_path = sys.argv[1], sys.argv[2]

try:
    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)
except json.JSONDecodeError as e:
    print(f"FAIL: {settings_path} is not valid JSON: {e}", file=sys.stderr)
    sys.exit(1)

enabled = (
    isinstance(settings, dict)
    and isinstance(settings.get("plugins"), dict)
    and isinstance(settings["plugins"].get("pstack"), dict)
    and settings["plugins"]["pstack"].get("enabled") is True
)
if not enabled:
    print(
        f"FAIL: {settings_path} must be JSON with plugins.pstack.enabled true",
        file=sys.stderr,
    )
    sys.exit(1)

text = open(models_path, encoding="utf-8").read()
# Drop YAML frontmatter so description/alwaysApply are not treated as settings.
if text.startswith("---"):
    end = text.find("\n---", 3)
    if end != -1:
        text = text[end + 4 :]
# Drop HTML comments, then whole-line # comments (dated grok-4.7 note lives here).
text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
active_lines = []
for line in text.splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    active_lines.append(stripped)

active = "\n".join(active_lines)
# Model slugs pstack skills hard-code today, plus nearby families.
slug = re.compile(
    r"\b(?:cursor-)?(?:grok|claude|gpt|composer|gemini|opus)[a-z0-9.+-]*\b",
    re.I,
)
found = slug.findall(active)
bad = [s for s in found if s != "grok-4.6"]
if bad:
    print(
        "FAIL: pstack-models.mdc active settings include models other than grok-4.6: "
        + ", ".join(dict.fromkeys(bad)),
        file=sys.stderr,
    )
    sys.exit(1)
if "grok-4.6" not in found:
    print(
        "FAIL: pstack-models.mdc has no active grok-4.6 setting",
        file=sys.stderr,
    )
    sys.exit(1)
print("PASS: pstack vendoring checks")
PY
