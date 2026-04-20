#!/usr/bin/env bash
set -e
cd "$HOME/.claude/skills"

echo "== before =="
find . -maxdepth 2 -name SKILL.md | sort

for name in brief-to-tasks design-brief design-flow design-review design-tokens grill-me information-architecture; do
  src="designer-skills/$name"
  if [ -f "$src/SKILL.md" ]; then
    if [ ! -d "$name" ]; then
      cp -r "$src" "$name"
      echo "added $name"
    else
      echo "skip $name (already installed)"
    fi
  else
    echo "MISS $name (no source)"
  fi
done

echo
echo "== after =="
find . -maxdepth 2 -name SKILL.md | sort
