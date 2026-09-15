"""Deterministic quotas; batch size limits structured-output length and provider cost."""
TYPES = ('single', 'multiple', 'judge', 'fill', 'written')
BATCH_SIZE = 5


def default_counts(total):
    if total < 3:
        return {'single': total}
    minority = max(1, total // 5)
    return {'single': total - minority * 2, 'multiple': minority, 'judge': minority}


def batches(counts):
    remaining = dict(counts)
    result, current = [], {}
    while any(remaining.values()):
        for kind in TYPES:
            if remaining.get(kind, 0):
                current[kind] = current.get(kind, 0) + 1
                remaining[kind] -= 1
                if sum(current.values()) == BATCH_SIZE:
                    result.append(current)
                    current = {}
    if current:
        result.append(current)
    return result
