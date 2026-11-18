# TODO

Known issues deliberately left alone for now (noted 2026-11-18, during demo prep).

## Duplicate interviews in the live database

Don't fix these from demo work. Review them by hand later, then delete the
extra copy (and its duplicate person record) from the Interviews page.

- **Interviews 17 and 19**: both "Navy physicist / researcher" (inertial
  navigation), same transcript length. Very likely the same interview saved twice.
- **Interviews 28 and 29**: both Jacob Widman (2026-09-16), each linked to its
  own person record (people 22 and 23).

## Interviews without an interviewee linked

Interviews 12, 17, 19 and 20 have no interviewee linked. Since the demo
hardening, the Interviews page no longer guesses names for these with AI on
page load. Use **Suggest titles from transcripts** on that page, or link a
person through processing, when convenient.
