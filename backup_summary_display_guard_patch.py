"""Keep backup Staff digests compact while the attached TXT remains complete."""

import backup_staff_summary_patch as summary


_original_short = summary._short


def _compact_short(lines, limit=4):
    return _original_short(lines, limit=min(int(limit), 4))


summary._short = _compact_short
print("AJAP backup Staff: resumen compacto; detalle completo queda en TXT")
