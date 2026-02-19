---
description: Always verify calendar date and market status before trading assumptions
---

# Calendar and Market Status Check

> **Rule version:** 2026-02-19T07:01:00

Before making any assumptions about:
- Market hours (open, after-hours, pre-market)
- Trading day status (weekday vs weekend)
- Holiday schedules
- What day/date it is

**ALWAYS:**
1. Check the current local time provided in ADDITIONAL_METADATA
2. **CALCULATE** the day of week from the date (don't guess - use a calendar calculation)
3. Consider US market holidays
4. Only then make claims about market status

**US Markets are CLOSED:**
- Saturday and Sunday (all day)
- New Year's Day (Jan 1)
- MLK Day (3rd Monday Jan)
- Presidents Day (3rd Monday Feb)
- Good Friday
- Memorial Day (last Monday May)
- Juneteenth (June 19)
- Independence Day (July 4)
- Labor Day (1st Monday Sep)
- Thanksgiving Day (4th Thursday Nov)
- Christmas (Dec 25)

**Market Hours (Eastern Time):**
- Pre-market: 4:00 AM - 9:30 AM
- Regular: 9:30 AM - 4:00 PM
- After-hours: 4:00 PM - 8:00 PM
