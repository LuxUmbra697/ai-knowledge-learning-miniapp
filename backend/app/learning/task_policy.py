"""Shared worker/admission policy; no SDK or queue retry multiplication."""
import re

QUIZ_MAX_ATTEMPTS = 10
QUIZ_RUNTIME_SECONDS = 600
QUIZ_INPUT_BYTES = 160000
QUIZ_TOKENS = 60000
DEFAULT_RUNTIME_SECONDS = 180


def quiz_stage(stage):
    return stage == 'quiz' or re.fullmatch(r'quiz_batch_[1-4]', stage) is not None


def quiz_attempts(state):
    return sum(count for stage, count in state.get('attempts', {}).items() if quiz_stage(stage))


def runtime_seconds(kind):
    return QUIZ_RUNTIME_SECONDS if kind == 'quiz' else DEFAULT_RUNTIME_SECONDS
