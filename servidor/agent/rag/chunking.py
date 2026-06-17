"""Code-aware chunking strategies for the RAG pipeline."""

import os
import re
from typing import Dict, List

# Extensions considered as code files
_CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cs', '.go',
    '.rb', '.php', '.rs', '.c', '.cpp', '.h', '.hpp', '.swift',
}

_MARKDOWN_EXTENSIONS = {'.md', '.mdx', '.rst', '.wiki', '.txt'}


def chunk_code_file(
    content: str, file_path: str, max_chunk_size: int = 1500
) -> List[Dict]:
    """Split code by function/class boundaries using regex patterns."""
    # Pattern matches common function/class/method definitions
    boundary_pattern = re.compile(
        r'^(?='
        r'(?:export\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+'  # JS/TS
        r'|(?:def|class|async\s+def)\s+'                                    # Python
        r'|(?:public|private|protected|static)\s+'                          # Java/C#
        r')',
        re.MULTILINE,
    )

    splits = boundary_pattern.split(content)
    # Re-attach the boundary text that was consumed by lookahead
    positions = [m.start() for m in boundary_pattern.finditer(content)]

    if not positions:
        # No boundaries found — fall back to line-based splitting
        return _chunk_by_lines(content, file_path, max_chunk_size)

    chunks = []
    # Text before first boundary
    if positions[0] > 0:
        preamble = content[: positions[0]].strip()
        if preamble:
            chunks.append(preamble)

    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(content)
        segment = content[pos:end].strip()
        if segment:
            chunks.append(segment)

    # Merge small chunks, split large ones
    ext = os.path.splitext(file_path)[1]
    language = ext.lstrip('.') if ext else 'text'
    return _finalize_chunks(chunks, file_path, language, max_chunk_size)


def chunk_markdown_file(
    content: str, file_path: str, max_chunk_size: int = 1500
) -> List[Dict]:
    """Split markdown by heading boundaries."""
    heading_pattern = re.compile(r'^(#{1,6}\s+.+)$', re.MULTILINE)
    positions = [m.start() for m in heading_pattern.finditer(content)]

    if not positions:
        return _chunk_by_lines(content, file_path, max_chunk_size)

    chunks = []
    if positions[0] > 0:
        preamble = content[: positions[0]].strip()
        if preamble:
            chunks.append(preamble)

    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(content)
        section = content[pos:end].strip()
        if section:
            chunks.append(section)

    return _finalize_chunks(chunks, file_path, 'markdown', max_chunk_size)


def chunk_file(content: str, file_path: str) -> List[Dict]:
    """Dispatch to the appropriate chunking strategy based on file extension."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext in _MARKDOWN_EXTENSIONS:
        return chunk_markdown_file(content, file_path)
    if ext in _CODE_EXTENSIONS:
        return chunk_code_file(content, file_path)

    # Default: treat as plain text, chunk by lines
    return _chunk_by_lines(content, file_path, max_chunk_size=1500)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chunk_by_lines(
    content: str, file_path: str, max_chunk_size: int
) -> List[Dict]:
    """Simple line-based chunking for files without clear boundaries."""
    lines = content.split('\n')
    chunks: List[str] = []
    current: List[str] = []
    current_size = 0

    for line in lines:
        line_size = len(line) + 1  # +1 for newline
        if current_size + line_size > max_chunk_size and current:
            chunks.append('\n'.join(current))
            current = []
            current_size = 0
        current.append(line)
        current_size += line_size

    if current:
        chunks.append('\n'.join(current))

    ext = os.path.splitext(file_path)[1]
    language = ext.lstrip('.') if ext else 'text'
    return [
        {
            "content": chunk,
            "metadata": {
                "source": file_path,
                "chunk_index": i,
                "language": language,
            },
        }
        for i, chunk in enumerate(chunks)
        if chunk.strip()
    ]


def _finalize_chunks(
    raw_chunks: List[str],
    file_path: str,
    language: str,
    max_chunk_size: int,
) -> List[Dict]:
    """Merge small chunks, split oversized ones, and add metadata."""
    merged: List[str] = []
    buffer = ""

    for chunk in raw_chunks:
        if len(buffer) + len(chunk) + 1 <= max_chunk_size:
            buffer = f"{buffer}\n{chunk}" if buffer else chunk
        else:
            if buffer:
                merged.append(buffer)
            # If this single chunk is too large, split it by lines
            if len(chunk) > max_chunk_size:
                lines = chunk.split('\n')
                sub_buf = ""
                for line in lines:
                    if len(sub_buf) + len(line) + 1 > max_chunk_size and sub_buf:
                        merged.append(sub_buf)
                        sub_buf = ""
                    sub_buf = f"{sub_buf}\n{line}" if sub_buf else line
                buffer = sub_buf
            else:
                buffer = chunk

    if buffer:
        merged.append(buffer)

    return [
        {
            "content": chunk,
            "metadata": {
                "source": file_path,
                "chunk_index": i,
                "language": language,
            },
        }
        for i, chunk in enumerate(merged)
        if chunk.strip()
    ]
