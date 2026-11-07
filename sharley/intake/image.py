"""Image -> structured description via a vision-capable model."""
from pydantic import BaseModel, Field

from sharley.harness import FallbackChain, Step

MAX_IMAGE_BYTES = 8_000_000
_PNG, _JPG = b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"


class ImageIn(BaseModel):
    note: str = "Describe this diagram or sketch."


class ImageDescription(BaseModel):
    entities: list[str] = Field(default_factory=list)
    screens: list[str] = Field(default_factory=list)
    flows: list[str] = Field(default_factory=list)
    arrows: list[str] = Field(default_factory=list)


DESCRIBE = Step("describe_image", "Describe the hand-drawn diagram, wireframe or screenshot. List entities, "
                "screens, user flows, and arrows (source -> target). Only report what is visible; do not invent.",
                ImageIn, ImageDescription, tier="strong")


def validate_image(data: bytes) -> bytes:
    if not (data.startswith(_PNG) or data.startswith(_JPG)):
        raise ValueError("unsupported image: only PNG and JPEG are accepted")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("image too large")
    return data


def describe_image(chain: FallbackChain, data: bytes) -> str:
    d = DESCRIBE.run(chain, ImageIn(), images=[validate_image(data)])
    lines = []
    for title, items in (("Entity", d.entities), ("Screen", d.screens), ("Flow", d.flows), ("Arrow", d.arrows)):
        lines += [f"{title}: {i}" for i in items]
    if not lines:
        raise ValueError("no content could be read from the image")
    return "\n".join(lines)
