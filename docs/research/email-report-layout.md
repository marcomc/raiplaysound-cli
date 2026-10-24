# Compact email report layout

## Findings

- Litmus recommends responsive email layouts that adapt with CSS media queries.
  For long messages, it also recommends reducing visual clutter and using
  clear visual anchors such as headings, bullets, color, and bold type to make
  content easier to scan. These are practitioner recommendations from Litmus,
  not a client rendering specification.
- Gmail supports standard media queries for screen width, orientation, and
  resolution, but may ignore unsupported CSS properties. A compact email should
  therefore retain useful inline styles and a simple table-based fallback.

## Recommendation for the daily sync report

Use a single-line brand/report header, put status and episode count on one
compact summary line, and replace the separate bordered card for every episode
with a tight list separated by thin rules. Give each episode a prominent title
and one smaller metadata line for program and date. This preserves a strong
visual hierarchy while reducing repeated padding and card borders. Keep the
plain-text alternative in the same compact title-plus-metadata order.

## Sources

- [Litmus: Email design best practices](https://www.litmus.com/blog/email-design-best-practices),
  tips 2, 9, and 14: responsive media-query layouts, reduced visual clutter,
  and scannable visual anchors.
- [Google for Developers: Gmail CSS support](https://developers.google.com/workspace/gmail/design/css),
  “CSS media queries”: Gmail supports width, orientation, and resolution
  queries; unsupported CSS properties or selectors may be ignored.
