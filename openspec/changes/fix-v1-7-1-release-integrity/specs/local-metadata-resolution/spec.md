## ADDED Requirements

### Requirement: Meaningful embedded metadata has priority
The library scanner SHALL preserve meaningful embedded title, artist, and album tags over path-derived values.

#### Scenario: Complete embedded tags differ from folders
- **WHEN** a scanned file has meaningful embedded title, artist, and album tags
- **THEN** the database stores those embedded values unchanged

### Requirement: Structured paths repair incomplete display metadata
The scanner SHALL use a configured library root and an `artist/album/file` path to fill missing artist or album values and replace a generic `Track <number>` title with a meaningful filename stem.

#### Scenario: Artist tag is missing
- **WHEN** `Los Hermanos/Los Hermanos - Ya llego/Con Cristo.m4a` has album `Ya Llego`, no artist, and title `Track 05`
- **THEN** the stored display metadata is title `Con Cristo`, artist `Los Hermanos`, and album `Ya Llego`

#### Scenario: Path is too shallow
- **WHEN** a file without embedded artist metadata is not beneath both artist and album directories relative to a configured root
- **THEN** the stored artist remains `Unknown Artist`

### Requirement: Resolution is non-destructive and stable
Metadata resolution SHALL update only application database facts, SHALL NOT modify source audio files, and SHALL mark processed legacy rows so unchanged files are not repaired repeatedly.

#### Scenario: Legacy incomplete row is scanned
- **WHEN** a pre-migration row lacks the metadata-resolution completion marker
- **THEN** the scanner re-reads and resolves it once, records completion, and leaves file bytes and modification time unchanged
