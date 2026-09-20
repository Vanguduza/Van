"""Reading Kotlin source without being fooled by it.

One scanner, two callers. `kotlin_reachability.py` and
`tests/contracts/test_android_compiles_at_all.py` both needed to strip comments and string
literals before looking for symbols, and both did it with a sequence of regular
expressions — which cannot work, because in Kotlin each of those constructs can contain
the other.

The reachability gate's version failed visibly: a string containing `"*/*"`, the MIME
wildcard every Android file chooser passes, closed a block comment a KDoc had opened, and
the gate reported a live class as referenced by nothing. The compile gate's version had
the same shape and the opposite symptom — a string containing `//` truncated the line, so
a visibility violation on it would simply not be seen.

So the scanner lives here and neither file has its own. A shared bug is better than two
different ones, and this one has tests.
"""

from __future__ import annotations


def strip_noise(text: str) -> str:
    """Remove comments and string literals before counting references.

    A symbol named in a KDoc paragraph is documentation, not a call site. Counting it would
    make every well-documented dead class look alive — which is precisely the confusion this
    whole programme exists to correct.

    Done as one left-to-right pass rather than as a sequence of regular expressions,
    because the sequence had a hole and the hole was silent. Comments were stripped first,
    so a *string* containing comment punctuation — `"*/*"`, the MIME wildcard an
    `ACTION_OPEN_DOCUMENT` call passes — closed a block comment that had been opened by a
    KDoc hundreds of lines earlier. Everything between them vanished from the analysis,
    and the file that used it was reported as referencing nothing. The gate said a live
    class was dead, which is the one direction this tool must not be wrong in.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "*":
            depth = 1
            i += 2
            # Kotlin block comments nest, unlike Java's. A `/*` inside one closes on its
            # own `*/`, and a stripper that ignored that would end the comment early.
            while i < n and depth:
                if text[i] == "/" and i + 1 < n and text[i + 1] == "*":
                    depth += 1
                    i += 2
                elif text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                    depth -= 1
                    i += 2
                else:
                    i += 1
            out.append(" ")
            continue
        if ch == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                i += 1
            out.append(" ")
            continue
        if text.startswith('"""', i):
            i += 3
            while i < n and not text.startswith('"""', i):
                i += 1
            i += 3
            out.append(' "" ')
            continue
        if ch == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == "\\":
                    i += 1
                if i < n and text[i] == "\n":
                    break
                i += 1
            i += 1
            out.append(' "" ')
            continue
        out.append(ch)
        i += 1
    return "".join(out)
