"""The annotation list: what the chat model writes and the renderer draws.

Every annotation addresses the music by position (measure number, beat, staff,
pitch), never by pixel. See docs/annotation-spec.md.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

View = Literal["harmony", "voice_leading", "form"]
Role = Literal["student", "composer"]
Style = Literal["current", "abrsm", "figured_bass"]


class Position(BaseModel):
    """A moment in the score. `beat` is 1-based in the meter's beat unit (a dotted quarter in 12/8)."""

    model_config = ConfigDict(extra="forbid")

    measure: int
    beat: float = 1.0


class RangeEnd(BaseModel):
    """Where a range stops. Without `beat` the range runs to the end of the measure."""

    model_config = ConfigDict(extra="forbid")

    measure: int
    beat: float | None = None


class NoteRef(Position):
    """One note. `staff` (1 = top) and `pitch` ("Eb4") disambiguate simultaneous notes."""

    staff: int | None = None
    pitch: str | None = None


class Annotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    views: list[View] | None = Field(None, description="Views that show this; the default depends on the type")
    role: Role | None = Field(None, description="Show only for this role; omitted means both")
    callout: int | None = Field(None, description="Number of the commentary note that discusses this")


class Harmony(Annotation):
    type: Literal["harmony"]
    at: Position
    label: str = Field(description='Roman numeral in RomanText style, e.g. "I", "V65/ii", "viio7/V", "bII6"')
    function: Literal["T", "PD", "D"] | None = Field(None, description="Tonic, predominant or dominant")
    key: str | None = Field(None, description='Set where the local key starts or changes, e.g. "Eb" or "f"')


class Cadence(Annotation):
    type: Literal["cadence"]
    at: Position
    label: str = Field(description='e.g. "PAC", "IAC", "HC", "DC"')


class Phrase(Annotation):
    type: Literal["phrase"]
    start: Position
    end: RangeEnd
    label: str = ""


class Region(Annotation):
    """A stretch of music named for what it is built on rather than for a chord function."""

    type: Literal["region"]
    start: Position
    end: RangeEnd
    label: str = Field(description='e.g. "whole-tone", "E Dorian", "pentatonic", "parallel 9th chords", "pedal on G"')
    staff: int | None = Field(None, description="Draw the bracket at this staff (1 = top) when the region belongs to one instrument, e.g. a theme in the cello")


class NonChordTone(Annotation):
    type: Literal["nct"]
    note: NoteRef
    label: str = Field(description='Open Music Theory abbreviation, e.g. "PT" passing, "NT" neighbor, "SUS" suspension, "APP" appoggiatura, "ET", "ANT", "RET", "PED"; the older "P", "N", "S" are drawn as PT, NT, SUS')


# The words part_writing puts on its arrows (an unresolved seventh or leading tone). An arrow with any other label,
# or none, is an analysis mark the model draws (a resolution) and is not red.
FAULT_ARROW_LABELS = frozenset({"R"})  # Kelley's improper-resolution arrow


class VoiceLeading(Annotation):
    """A part-writing mark. Faults are drawn red (every line, ring and bracket, and an arrow labelled with a fault
    word); other arrows are analysis marks in magenta. The label names the fault, once per pair of voices."""

    type: Literal["voice_leading"]
    kind: Literal["arrow", "line", "ring", "bracket"] = Field(
        "arrow",
        description="arrow: a tendency tone to the note that follows (to_note); line: one voice of a parallel or "
        "direct interval, no arrowhead (to_note); ring: circle the note (from_note only); bracket: square bracket "
        "spanning two notes of one chord (to_note)")
    from_note: NoteRef
    to_note: NoteRef | None = None
    label: str = ""

    @model_validator(mode="after")
    def _needs_to_note(self):
        if (self.kind == "ring") == (self.to_note is not None):
            raise ValueError("a ring takes only from_note; every other kind needs to_note")
        return self


class Callout(Annotation):
    type: Literal["callout"]
    at: Position
    number: int


AnyAnnotation = Annotated[
    Harmony | Cadence | Phrase | Region | NonChordTone | VoiceLeading | Callout,
    Field(discriminator="type"),
]

DEFAULT_VIEWS: dict[str, set[str]] = {
    "harmony": {"harmony", "voice_leading"},
    "function": {"harmony"},  # the bands drawn from Harmony.function
    "cadence": {"harmony", "form"},
    "phrase": {"form"},
    "region": {"harmony", "form"},
    "nct": {"voice_leading"},
    "voice_leading": {"voice_leading"},
    "callout": {"harmony", "voice_leading", "form"},
}


class AnnotationList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    style: Style = "current"
    annotations: list[AnyAnnotation]

    def visible(self, kind: str, annotation: Annotation, view: str, role: str | None) -> bool:
        if role and annotation.role and annotation.role != role:
            return False
        if view == "all":
            return True
        return view in (annotation.views or DEFAULT_VIEWS[kind])
