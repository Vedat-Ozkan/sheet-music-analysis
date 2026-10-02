"""The annotation list: what the chat model writes and the renderer draws.

Every annotation addresses the music by position (measure number, beat, staff,
pitch), never by pixel. See docs/annotation-spec.md.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

View = Literal["harmony", "voice_leading", "form"]
Role = Literal["student", "composer"]


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


class NonChordTone(Annotation):
    type: Literal["nct"]
    note: NoteRef
    label: str = Field(description='e.g. "P" passing, "N" neighbor, "S" suspension, "APP" appoggiatura')


class VoiceLeading(Annotation):
    type: Literal["voice_leading"]
    from_note: NoteRef
    to_note: NoteRef
    label: str = ""


class Callout(Annotation):
    type: Literal["callout"]
    at: Position
    number: int


AnyAnnotation = Annotated[
    Harmony | Cadence | Phrase | NonChordTone | VoiceLeading | Callout,
    Field(discriminator="type"),
]

DEFAULT_VIEWS: dict[str, set[str]] = {
    "harmony": {"harmony", "voice_leading"},
    "function": {"harmony"},  # the bands drawn from Harmony.function
    "cadence": {"harmony", "form"},
    "phrase": {"form"},
    "nct": {"voice_leading"},
    "voice_leading": {"voice_leading"},
    "callout": {"harmony", "voice_leading", "form"},
}


class AnnotationList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    annotations: list[AnyAnnotation]

    def visible(self, kind: str, annotation: Annotation, view: str, role: str | None) -> bool:
        if role and annotation.role and annotation.role != role:
            return False
        if view == "all":
            return True
        return view in (annotation.views or DEFAULT_VIEWS[kind])
