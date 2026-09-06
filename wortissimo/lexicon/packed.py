"""Memory-compact immutable string set.

A Python set of the 2.15M germandict words costs ~227MB: every entry is a
separate str object plus a hash-table slot. The same data as one sorted
UTF-8 blob with an offset index is ~40MB, because there are no per-object
headers and no hash table.

This matters twice: the build has to coexist with CharSplit's 213MB ngram
model, and it has to run inside a container on a home server.

Lookup is a binary search over the offset index — O(log n) rather than
O(1), but a build does a few million lookups, not a few billion.
"""

from __future__ import annotations

from array import array
from collections.abc import Iterable, Iterator
from pathlib import Path

SEPARATOR = b"\n"
MAGIC = b"WPS1"


class PackedWordSet:
    """Immutable set of words backed by a sorted blob plus offsets."""

    __slots__ = ("_blob", "_offsets")

    def __init__(self, blob: bytes, offsets: array) -> None:
        self._blob = blob
        self._offsets = offsets

    @classmethod
    def build(cls, words: Iterable[str]) -> PackedWordSet:
        ordered = sorted(set(words))
        encoded = [w.encode("utf-8") for w in ordered]
        del ordered

        offsets = array("Q", [0])
        blob = bytearray()
        for item in encoded:
            blob += item
            blob += SEPARATOR
            offsets.append(len(blob))
        del encoded
        return cls(bytes(blob), offsets)

    def _word_at(self, index: int) -> bytes:
        start = self._offsets[index]
        end = self._offsets[index + 1] - len(SEPARATOR)
        return self._blob[start:end]

    def __contains__(self, word: object) -> bool:
        if not isinstance(word, str):
            return False
        target = word.encode("utf-8")
        low, high = 0, len(self._offsets) - 1
        while low < high:
            mid = (low + high) // 2
            if self._word_at(mid) < target:
                low = mid + 1
            else:
                high = mid
        return low < len(self._offsets) - 1 and self._word_at(low) == target

    def word_at(self, index: int) -> str:
        """Decode the word stored at `index` (0 <= index < len(self))."""
        return self._word_at(index).decode("utf-8")

    def __len__(self) -> int:
        return len(self._offsets) - 1

    def __iter__(self) -> Iterator[str]:
        for index in range(len(self)):
            yield self._word_at(index).decode("utf-8")

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            fh.write(MAGIC)
            fh.write(len(self._offsets).to_bytes(8, "little"))
            fh.write(self._offsets.tobytes())
            fh.write(self._blob)

    @classmethod
    def load(cls, path: Path) -> PackedWordSet:
        with path.open("rb") as fh:
            if fh.read(len(MAGIC)) != MAGIC:
                raise ValueError(f"{path} is not a packed word set")
            count = int.from_bytes(fh.read(8), "little")
            offsets = array("Q")
            offsets.frombytes(fh.read(count * offsets.itemsize))
            return cls(fh.read(), offsets)
