#!/usr/bin/env bash
# Human-in-the-loop reproduction loop.
# Copy this file, edit the steps below, and run it.
# The agent runs the script; the user follows prompts in their terminal.
#
# Usage:
#   bash hitl-loop.template.sh
#
# Two helpers:
#   step "<instruction>"          -> show instruction, wait for Enter
#   capture VAR "<question>"      -> show question, read response into VAR
#
# At the end, captured values are printed as KEY=VALUE for the agent to parse.

set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- edit below ---------------------------------------------------------

step "Replace this with the exact human action to perform."

capture RESULT "Replace this with the specific observation to capture."

capture NOTES "Paste any relevant details, logs, IDs, or 'none':"

# --- edit above ---------------------------------------------------------

printf '\n--- Captured ---\n'
printf 'RESULT=%s\n' "$RESULT"
printf 'NOTES=%s\n' "$NOTES"
