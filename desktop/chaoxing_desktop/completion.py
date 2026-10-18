"""Completion validation requires explicit platform blank identities."""
import json


def completion_parts(answer, blank_count):
    if type(blank_count) is not int or blank_count < 1 or blank_count > 100:
        return None
    if isinstance(answer, str):
        answer = answer.strip()
        if answer.startswith('['):
            try:
                answer = json.loads(answer)
            except ValueError:
                return None
        elif blank_count == 1:
            answer = [answer]
        else:
            return None  # Do not guess delimiters inside prose/formulas.
    if not isinstance(answer, list) or len(answer) != blank_count:
        return None
    if not all(isinstance(part, str) and part.strip() for part in answer):
        return None
    return [part.strip() for part in answer]
