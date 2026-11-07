# Project rules

## Anonymous data only

Tests, fixtures, code comments, docs and commit messages must not contain data
from real flights. Real portal responses are fine for learning the format, but
anonymize every value before it lands in the repo:

- Flight numbers, tail numbers, flight/session ids: made up (e.g. `AAL123`, `N123AA`).
- Dates and times: made up, not the day of a real flight.
- Positions, altitudes, speeds: made up (plausible, not copied from a real track).
- Device data (IP, MAC, device GUID, policy names): never, not even made up unless a test needs the key.
- Airport codes and airport coordinates are public reference data and may be used,
  but don't pair them with a real flight's number/date.

Saved history (`history/`) is user data and stays out of git (see `.gitignore`).
