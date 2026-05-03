from datetime import date
import calendar

def next_due_date(occurred_on: date, due_day: int) -> date:
    y, m = occurred_on.year, occurred_on.month
    last_day = calendar.monthrange(y, m)[1]
    d = min(due_day, last_day)
    candidate = date(y, m, d)
    if candidate >= occurred_on:
        return candidate

    if m == 12:
        y, m = y + 1, 1
    else:
        m += 1
    last_day = calendar.monthrange(y, m)[1]
    d = min(due_day, last_day)
    return date(y, m, d)
