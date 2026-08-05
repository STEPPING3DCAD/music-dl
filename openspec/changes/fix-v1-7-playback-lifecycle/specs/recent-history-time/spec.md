## ADDED Requirements

### Requirement: Recent history uses browser milliseconds
The system SHALL normalize server epoch-second `played_at` values to epoch milliseconds before merging them with browser history.

#### Scenario: Server returns epoch seconds
- **WHEN** recent history contains a positive `played_at` value below `10,000,000,000`
- **THEN** the browser multiplies it by 1000 before sorting, grouping, filtering, or clearing

#### Scenario: Browser value is already milliseconds
- **WHEN** recent history contains a `played_at` value at or above `10,000,000,000`
- **THEN** normalization leaves it unchanged

#### Scenario: Same track exists locally and on the server
- **WHEN** duplicate track keys are merged
- **THEN** the actually newer normalized timestamp wins

### Requirement: Time filters use normalized values
The system SHALL classify current, weekly, and older history and clear only entries older than 30 days using normalized timestamps.

#### Scenario: Current server play
- **WHEN** the server reports a play from today in epoch seconds
- **THEN** the UI groups and counts it as Today

#### Scenario: Clear old history
- **WHEN** the user clears entries older than 30 days
- **THEN** recent normalized entries remain and only older entries are removed
