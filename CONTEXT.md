# Local Music Library

Terms used to describe how music-dl identifies and presents local releases without changing the underlying audio files.

## Language

**Release**:
A specific published edition of an album, such as the standard, extended, remastered, or clean edition.
_Avoid_: Album version, release group

**Local Album Group**:
Tracks currently grouped by their exact embedded album title before duplicate-release assessment.
_Avoid_: Album, release

**Duplicate Release Candidate**:
Two Local Album Groups that may represent copies or partial copies of the same Release.
_Avoid_: Duplicate cover, duplicate album

**Recording Slot**:
One represented track position within a Local Album Group after physical copies are collapsed, carrying zero, one, or conflicting recording identifiers.
_Avoid_: File, duplicate track

**Grouping Assessment**:
An explainable confidence result built from corroborating evidence, source diversity, and contradictions for one Duplicate Release Candidate.
_Avoid_: AI decision, fuzzy match

**Evidence Family**:
A score category whose related signals share a contribution cap so one kind of evidence cannot inflate confidence.
_Avoid_: Evidence Source, field count

**Evidence Source**:
The provenance from which evidence was obtained, used to measure corroboration across independent origins.
_Avoid_: Evidence Family, field

**Grouping Decision**:
The automatic or user-confirmed instruction to present two Local Album Groups as one Release card or keep them separate.
_Avoid_: Merge, deduplication
