#!/usr/bin/env bash
set -eu
SRC="$HOME/.claude/skills"
DST="/mnt/c/Users/MSI/Documents/Med_LLM/medai-platform/.claude/skills"
mkdir -p "$DST"

NAMES=(
  baseline-ui brief-to-tasks composition-patterns deploy-to-vercel
  design-brief design-flow design-review design-tokens
  fixing-accessibility fixing-metadata fixing-motion-performance
  frontend-design grill-me information-architecture
  react-best-practices react-native-skills react-view-transitions
  vercel-cli-with-tokens web-artifacts-builder web-design-guidelines
)

for name in "${NAMES[@]}"; do
  if [ -f "$SRC/$name/SKILL.md" ]; then
    if [ ! -d "$DST/$name" ]; then
      cp -r "$SRC/$name" "$DST/$name"
      echo "added $name"
    else
      echo "exists $name"
    fi
  else
    echo "MISS $name"
  fi
done

# Add the 14 superpowers sub-skills
if [ -d "$SRC/superpowers/skills" ]; then
  for d in "$SRC/superpowers/skills"/*/; do
    spname=$(basename "$d")
    target="$DST/sp-$spname"
    if [ -f "$d/SKILL.md" ] && [ ! -d "$target" ]; then
      cp -r "$d" "$target"
      echo "added sp-$spname"
    fi
  done
fi

echo
echo "=== project skills dir ==="
ls "$DST" | sort
echo "count: $(ls -d "$DST"/*/ | wc -l)"
