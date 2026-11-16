"""Throwaway round-trip writer for experiments: py_l5x load -> (modify) -> L5X text."""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from py_l5x import load  # noqa: E402
from py_l5x.parsers.utils import CDATA_TAG  # noqa: E402


def to_text(root: ET.Element) -> str:
    s = ET.tostring(root, encoding="unicode")

    def back(m):
        t = m.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        return "<![CDATA[" + t.replace("]]>", "]]]]><![CDATA[>") + "]]>"

    s = re.sub(rf"<{CDATA_TAG}>(.*?)</{CDATA_TAG}>", back, s, flags=re.S)
    s = s.replace(f"<{CDATA_TAG} />", "<![CDATA[]]>")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + s


def write(project, path, crlf=True, bom=True):
    txt = to_text(project._root)
    if crlf:
        txt = txt.replace("\r\n", "\n").replace("\n", "\r\n")
    data = txt.encode("utf-8")
    Path(path).write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
