"""Generate SDK import experiments. Usage: python gen.py exp01 [exp02 ...]."""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
BASE_ACD = "C:/Users/zwood/ldsdk/projects/base/example_base.ACD"
CTRL = "Example_PLC"
DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def env(
    target_type,
    target_name,
    inner,
    *,
    root_attrs=None,
    decl=True,
    ctrl=CTRL,
    ctrl_use='Use="Context" ',
    extra_root="",
):
    attrs = (
        root_attrs
        if root_attrs is not None
        else (
            f'SchemaRevision="1.0" SoftwareRevision="37.00" TargetName="{target_name}" '
            f'TargetType="{target_type}" ContainsContext="true"'
        )
    )
    return (
        (DECL if decl else "")
        + f"<RSLogix5000Content {attrs}{extra_root}>\n"
        + f'<Controller {ctrl_use}Name="{ctrl}">\n{inner}\n</Controller>\n</RSLogix5000Content>\n'
    )


def ctag(xml):
    """Wrap controller tag(s)."""
    return f'<Tags Use="Context">\n{xml}\n</Tags>'


def ptag(prog, xml):
    return (
        f'<Programs Use="Context"><Program Use="Context" Name="{prog}">'
        f'<Tags Use="Context">\n{xml}\n</Tags></Program></Programs>'
    )


def cd(s):
    return f"<![CDATA[{s}]]>"


DINT_DEC = '<Data Format="Decorated"><DataValue DataType="DINT" Radix="Decimal" Value="{v}"/></Data>'


def dint_tag(name, v=0, use='Use="Target" ', data=None):
    d = DINT_DEC.format(v=v) if data is None else data
    return (
        f'<Tag {use}Name="{name}" TagType="Base" DataType="DINT" Radix="Decimal" '
        f'Constant="false" ExternalAccess="Read/Write">{d}</Tag>'
    )


class Exp:
    def __init__(self, run, base=BASE_ACD):
        self.run, self.base, self.steps, self.files = run, base, [], {}
        self.dir = HERE / run

    def case(
        self,
        cid,
        content,
        *,
        xpath="Controller",
        coll="overwrite",
        op="import",
        bom=False,
        crlf=False,
        export=None,
        **kw,
    ):
        fname = f"{cid}.L5X"
        if crlf:
            content = content.replace("\r\n", "\n").replace("\n", "\r\n")
        data = content.encode("utf-8")
        if bom:
            data = b"\xef\xbb\xbf" + data
        self.files[fname] = data
        st = {"id": cid, "op": op, "file": fname, "xpath": xpath}
        if op == "import":
            st["coll"] = coll
        st.update(kw)
        self.steps.append(st)
        for i, xp in enumerate(export or []):
            self.export(f"{cid}_x{i}", xp)

    def export(self, name, xpath):
        self.steps.append(
            {"id": f"x_{name}", "op": "export", "xpath": xpath, "name": name}
        )

    def raw(self, **st):
        self.steps.append(st)

    def write(self):
        self.dir.mkdir(exist_ok=True)
        for f in self.dir.glob("*.L5X"):
            f.unlink()
        for n, d in self.files.items():
            (self.dir / n).write_bytes(d)
        m = {
            "run": self.run,
            "base": self.base,
            "dir": f"C:/Users/zwood/ldsdk/projects/{self.run}",
            "steps": self.steps,
        }
        (self.dir / "manifest.json").write_text(json.dumps(m, indent=1))
        print(f"{self.run}: {len(self.files)} files, {len(self.steps)} steps")


def CT(name):
    return f"Controller/Tags/Tag[@Name='{name}']"


# ---------------------------------------------------------------------------
def exp01():
    """Envelope variations + tag data formats."""
    e = Exp("exp01")
    # --- Envelope (each imports one DINT tag) ---
    e.case(
        "E01_bom_crlf",
        env("Tag", "E01", ctag(dint_tag("E01", 1))),
        bom=True,
        crlf=True,
        export=[CT("E01")],
    )
    e.case(
        "E02_nodecl",
        env("Tag", "E02", ctag(dint_tag("E02", 2)), decl=False),
        export=[CT("E02")],
    )
    e.case(
        "E03_bare_root",
        env("Tag", "E03", ctag(dint_tag("E03", 3)), root_attrs=""),
        export=[CT("E03")],
    )
    e.case(
        "E04_schema_only",
        env("Tag", "E04", ctag(dint_tag("E04", 4)), root_attrs='SchemaRevision="1.0"'),
        export=[CT("E04")],
    )
    e.case(
        "E05_rev_newer",
        env(
            "Tag",
            "E05",
            ctag(dint_tag("E05", 5)),
            root_attrs='SchemaRevision="1.0" SoftwareRevision="38.00" TargetName="E05" TargetType="Tag" ContainsContext="true"',
        ),
        export=[CT("E05")],
    )
    e.case(
        "E06_rev_older",
        env(
            "Tag",
            "E06",
            ctag(dint_tag("E06", 6)),
            root_attrs='SchemaRevision="1.0" SoftwareRevision="30.00" TargetName="E06" TargetType="Tag" ContainsContext="true"',
        ),
        export=[CT("E06")],
    )
    e.case(
        "E07_ctrl_name_mismatch",
        env("Tag", "E07", ctag(dint_tag("E07", 7)), ctrl="SomeOtherPLC"),
        export=[CT("E07")],
    )
    e.case(
        "E08_no_use_attrs",
        env("Tag", "E08", f"<Tags>{dint_tag('E08', 8, use='')}</Tags>", ctrl_use=""),
        export=[CT("E08")],
    )
    e.case(
        "E09_contains_ctx_false",
        env(
            "Tag",
            "E09",
            ctag(dint_tag("E09", 9)),
            root_attrs='SchemaRevision="1.0" SoftwareRevision="37.00" TargetName="E09" TargetType="Tag" ContainsContext="false"',
        ),
        export=[CT("E09")],
    )
    e.case(
        "E10_multi_target",
        env(
            "Tag",
            "E10a",
            ctag(dint_tag("E10a", 10) + dint_tag("E10b", 11) + dint_tag("E10c", 12)),
        ),
        export=[CT("E10a"), CT("E10b"), CT("E10c")],
    )
    e.case(
        "E11_multi_nouse",
        env(
            "Tag",
            "E11a",
            f"<Tags>{dint_tag('E11a', 1, use='')}{dint_tag('E11b', 2, use='')}</Tags>",
            ctrl_use="",
        ),
        export=[CT("E11a"), CT("E11b")],
    )
    e.case(
        "E12_target_type_mismatch",
        env("DataType", "E12", ctag(dint_tag("E12", 12))),
        export=[CT("E12")],
    )

    # --- DINT data formats ---
    e.case(
        "T02_l5k_only",
        env(
            "Tag",
            "T02",
            ctag(dint_tag("T02", data=f'<Data Format="L5K">{cd("42")}</Data>')),
        ),
        export=[CT("T02")],
    )
    e.case(
        "T03_no_data",
        env("Tag", "T03", ctag(dint_tag("T03", data=""))),
        export=[CT("T03")],
    )
    e.case(
        "T04_both_disagree",
        env(
            "Tag",
            "T04",
            ctag(
                dint_tag(
                    "T04",
                    data=f'<Data Format="L5K">{cd("111")}</Data>'
                    + DINT_DEC.format(v=222),
                )
            ),
        ),
        export=[CT("T04")],
    )
    e.case(
        "T04b_both_disagree_dec_first",
        env(
            "Tag",
            "T04b",
            ctag(
                dint_tag(
                    "T04b",
                    data=DINT_DEC.format(v=222)
                    + f'<Data Format="L5K">{cd("111")}</Data>',
                )
            ),
        ),
        export=[CT("T04b")],
    )
    e.case(
        "T15_minimal_attrs",
        env("Tag", "T15", ctag('<Tag Use="Target" Name="T15" DataType="DINT"/>')),
        export=[CT("T15")],
    )
    e.case(
        "T15b_minimal_attrs_val",
        env(
            "Tag",
            "T15b",
            ctag(
                '<Tag Use="Target" Name="T15b" DataType="DINT"><Data Format="Decorated"><DataValue DataType="DINT" Value="77"/></Data></Tag>'
            ),
        ),
        export=[CT("T15b")],
    )
    e.case(
        "T20_bad_value",
        env("Tag", "T20", ctag(dint_tag("T20", "abc"))),
        export=[CT("T20")],
    )
    e.case(
        "T20b_hex_value",
        env("Tag", "T20b", ctag(dint_tag("T20b", "16#FF"))),
        export=[CT("T20b")],
    )
    e.case(
        "T25_real",
        env(
            "Tag",
            "T25",
            ctag(
                '<Tag Use="Target" Name="T25" DataType="REAL" Radix="Float"><Data Format="Decorated"><DataValue DataType="REAL" Radix="Float" Value="1.5"/></Data></Tag>'
            ),
        ),
        export=[CT("T25")],
    )

    # --- TIMER / COUNTER ---
    tmr = lambda n, data: (
        f'<Tag Use="Target" Name="{n}" TagType="Base" DataType="TIMER" Constant="false" ExternalAccess="Read/Write">{data}</Tag>'
    )  # noqa: E731
    e.case(
        "T05_timer_nodata", env("Tag", "T05", ctag(tmr("T05", ""))), export=[CT("T05")]
    )
    e.case(
        "T06_timer_pre_only",
        env(
            "Tag",
            "T06",
            ctag(
                tmr(
                    "T06",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="5000"/></Structure></Data>',
                )
            ),
        ),
        export=[CT("T06")],
    )
    e.case(
        "T06b_timer_pre_bare",
        env(
            "Tag",
            "T06b",
            ctag(
                tmr(
                    "T06b",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="PRE" Value="2500"/></Structure></Data>',
                )
            ),
        ),
        export=[CT("T06b")],
    )
    e.case(
        "T06c_timer_dn_only",
        env(
            "Tag",
            "T06c",
            ctag(
                tmr(
                    "T06c",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="DN" DataType="BOOL" Value="1"/></Structure></Data>',
                )
            ),
        ),
        export=[CT("T06c")],
    )
    e.case(
        "T07_timer_full",
        env(
            "Tag",
            "T07",
            ctag(
                tmr(
                    "T07",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="1000"/><DataValueMember Name="ACC" DataType="DINT" Radix="Decimal" Value="10"/><DataValueMember Name="EN" DataType="BOOL" Value="1"/><DataValueMember Name="TT" DataType="BOOL" Value="0"/><DataValueMember Name="DN" DataType="BOOL" Value="1"/></Structure></Data>',
                )
            ),
        ),
        export=[CT("T07")],
    )
    e.case(
        "T08_timer_l5k",
        env(
            "Tag",
            "T08",
            ctag(tmr("T08", f'<Data Format="L5K">{cd("[0,3000,0]")}</Data>')),
        ),
        export=[CT("T08")],
    )
    e.case(
        "T13_timer_bogus_member",
        env(
            "Tag",
            "T13",
            ctag(
                tmr(
                    "T13",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="PRE" DataType="DINT" Value="9"/><DataValueMember Name="BOGUS" DataType="DINT" Value="1"/></Structure></Data>',
                )
            ),
        ),
        export=[CT("T13")],
    )
    e.case(
        "T13b_timer_wrong_member_type",
        env(
            "Tag",
            "T13b",
            ctag(
                tmr(
                    "T13b",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="PRE" DataType="REAL" Value="9.5"/></Structure></Data>',
                )
            ),
        ),
        export=[CT("T13b")],
    )
    e.case(
        "T17_counter_pre",
        env(
            "Tag",
            "T17",
            ctag(
                '<Tag Use="Target" Name="T17" DataType="COUNTER"><Data Format="Decorated"><Structure DataType="COUNTER"><DataValueMember Name="PRE" Value="12"/></Structure></Data></Tag>'
            ),
        ),
        export=[CT("T17")],
    )
    e.case(
        "T19_timer_desc_comments",
        env(
            "Tag",
            "T19",
            ctag(
                tmr(
                    "T19",
                    f'<Description>{cd("timer desc")}</Description><Comments><Comment Operand=".PRE">{cd("preset comment")}</Comment><Comment Operand=".DN">{cd("done comment")}</Comment></Comments>',
                )
            ),
        ),
        export=[CT("T19")],
    )

    # --- UDT / AOI / array / string ---
    e.case(
        "T09_udt_partial",
        env(
            "Tag",
            "T09",
            ctag(
                '<Tag Use="Target" Name="T09" DataType="A_UDT"><Data Format="Decorated"><Structure DataType="A_UDT"><DataValueMember Name="a_dint" Value="7"/><DataValueMember Name="a_Bool" Value="1"/><StructureMember Name="a_nested_UDT" DataType="simple_udt"><DataValueMember Name="lint" Value="99"/></StructureMember><ArrayMember Name="an_array" DataType="REAL" Dimensions="4"><Element Index="[2]" Value="2.5"/></ArrayMember></Structure></Data></Tag>'
            ),
        ),
        export=[CT("T09")],
    )
    e.case(
        "T10_udt_nodata",
        env("Tag", "T10", ctag('<Tag Use="Target" Name="T10" DataType="A_UDT"/>')),
        export=[CT("T10")],
    )
    e.case(
        "T11_string_fmt",
        env(
            "Tag",
            "T11",
            ctag(
                f'<Tag Use="Target" Name="T11" DataType="STRING"><Data Format="String" Length="5">{cd("'hello'")}</Data></Tag>'
            ),
        ),
        export=[CT("T11")],
    )
    e.case(
        "T11b_string_nodata",
        env("Tag", "T11b", ctag('<Tag Use="Target" Name="T11b" DataType="STRING"/>')),
        export=[CT("T11b")],
    )
    e.case(
        "T11c_string_nolen",
        env(
            "Tag",
            "T11c",
            ctag(
                f'<Tag Use="Target" Name="T11c" DataType="STRING"><Data Format="String">{cd("'abc'")}</Data></Tag>'
            ),
        ),
        export=[CT("T11c")],
    )
    e.case(
        "T11d_custom_string",
        env(
            "Tag",
            "T11d",
            ctag(
                f'<Tag Use="Target" Name="T11d" DataType="robotAlarmCode"><Data Format="String" Length="3">{cd("'xyz'")}</Data></Tag>'
            ),
        ),
        export=[CT("T11d")],
    )
    e.case(
        "T12_array_sparse",
        env(
            "Tag",
            "T12",
            ctag(
                '<Tag Use="Target" Name="T12" DataType="DINT" Dimensions="5"><Data Format="Decorated"><Array DataType="DINT" Dimensions="5"><Element Index="[0]" Value="10"/><Element Index="[3]" Value="13"/></Array></Data></Tag>'
            ),
        ),
        export=[CT("T12")],
    )
    e.case(
        "T12b_array_nodata",
        env(
            "Tag",
            "T12b",
            ctag('<Tag Use="Target" Name="T12b" DataType="TIMER" Dimensions="3"/>'),
        ),
        export=[CT("T12b")],
    )
    e.case(
        "T12c_udt_array_sparse",
        env(
            "Tag",
            "T12c",
            ctag(
                '<Tag Use="Target" Name="T12c" DataType="TIMER" Dimensions="3"><Data Format="Decorated"><Array DataType="TIMER" Dimensions="3"><Element Index="[1]"><Structure DataType="TIMER"><DataValueMember Name="PRE" Value="111"/></Structure></Element></Array></Data></Tag>'
            ),
        ),
        export=[CT("T12c")],
    )
    e.case(
        "T14_unknown_type",
        env("Tag", "T14", ctag('<Tag Use="Target" Name="T14" DataType="NoSuchType"/>')),
        export=[CT("T14")],
    )
    e.case(
        "T16_alias",
        env(
            "Tag",
            "T16",
            ctag('<Tag Use="Target" Name="T16" TagType="Alias" AliasFor="E01"/>'),
        ),
        export=[CT("T16")],
    )
    e.case(
        "T16b_alias_member",
        env(
            "Tag",
            "T16b",
            ctag('<Tag Use="Target" Name="T16b" TagType="Alias" AliasFor="T07.PRE"/>'),
        ),
        export=[CT("T16b")],
    )
    e.case(
        "T16c_alias_missing_target",
        env(
            "Tag",
            "T16c",
            ctag(
                '<Tag Use="Target" Name="T16c" TagType="Alias" AliasFor="DoesNotExist"/>'
            ),
        ),
        export=[CT("T16c")],
    )
    e.case(
        "T18_aoi_tag_partial",
        env(
            "Tag",
            "T18",
            ctag(
                '<Tag Use="Target" Name="T18" DataType="Debounce"><Data Format="Decorated"><Structure DataType="Debounce"><DataValueMember Name="onDelay" Value="500"/></Structure></Data></Tag>'
            ),
        ),
        export=[CT("T18")],
    )
    e.case(
        "T18b_aoi_tag_nodata",
        env("Tag", "T18b", ctag('<Tag Use="Target" Name="T18b" DataType="SeqCtrl"/>')),
        export=[CT("T18b")],
    )
    e.case(
        "T23_program_scope",
        env(
            "Tag",
            "T23",
            ptag("MainProgram", '<Tag Use="Target" Name="T23" DataType="TIMER"/>'),
        ),
        export=[
            "Controller/Programs/Program[@Name='MainProgram']/Tags/Tag[@Name='T23']"
        ],
    )
    e.case(
        "T23b_prog_scope_import_xpath",
        env("Tag", "T23b", ctag('<Tag Use="Target" Name="T23b" DataType="DINT"/>')),
        xpath="Controller/Programs/Program[@Name='MainProgram']/Tags",
        export=[
            "Controller/Programs/Program[@Name='MainProgram']/Tags/Tag[@Name='T23b']",
            CT("T23b"),
        ],
    )
    # --- Overwrite an existing tag with partial data ---
    e.case(
        "T30_overwrite_partial",
        env(
            "Tag",
            "T07",
            ctag(
                tmr(
                    "T07",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="ACC" Value="55"/></Structure></Data>',
                )
            ),
        ),
        export=[CT("T07")],
    )
    e.case(
        "T31_discard_existing",
        env(
            "Tag",
            "T06",
            ctag(
                tmr(
                    "T06",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="PRE" Value="1"/></Structure></Data>',
                )
            ),
        ),
        coll="discard",
        export=[CT("T06")],
    )
    e.case(
        "T32_cancel_existing",
        env("Tag", "T06b", ctag(tmr("T06b", ""))),
        coll="cancel",
        export=[CT("T06b")],
    )
    e.case(
        "T33_import_target_rename",
        env("Tag", "T33src", ctag('<Tag Use="Target" Name="T33src" DataType="DINT"/>')),
        op="import_target",
        xpath="Controller/Tags",
        target="T33renamed",
        export=[CT("T33renamed")],
    )
    e.case(
        "T34_import_target_existing",
        env(
            "Tag",
            "T05",
            ctag(
                tmr(
                    "T05",
                    '<Data Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="PRE" Value="4242"/></Structure></Data>',
                )
            ),
        ),
        op="import_target",
        xpath="Controller/Tags",
        target="T05",
        export=[CT("T05")],
    )
    e.raw(id="save", op="save_as", name="final.L5X")
    e.write()


TMR_FULL = (
    '<Structure DataType="TIMER"><DataValueMember Name="PRE" DataType="DINT" Value="{pre}"/>'
    '<DataValueMember Name="ACC" DataType="DINT" Value="{acc}"/><DataValueMember Name="EN" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="TT" DataType="BOOL" Value="0"/><DataValueMember Name="DN" DataType="BOOL" Value="0"/></Structure>'
)


def tmr(n, data="", use='Use="Target" ', extra=""):
    return f'<Tag {use}Name="{n}" DataType="TIMER"{extra}>{data}</Tag>'


def dec(x):
    return f'<Data Format="Decorated">{x}</Data>'


def exp01b():
    e = Exp("exp01b")
    H = 'TargetName="X" TargetType="Tag"'
    e.case(
        "F1_timer_full_noradix",
        env("Tag", "F1", ctag(tmr("F1", dec(TMR_FULL.format(pre=1234, acc=5))))),
        export=[CT("F1")],
    )
    e.case(
        "F2_timer_wrong_order",
        env(
            "Tag",
            "F2",
            ctag(
                tmr(
                    "F2",
                    dec(
                        '<Structure DataType="TIMER"><DataValueMember Name="ACC" DataType="DINT" Value="5"/><DataValueMember Name="PRE" DataType="DINT" Value="1234"/><DataValueMember Name="EN" DataType="BOOL" Value="0"/><DataValueMember Name="TT" DataType="BOOL" Value="0"/><DataValueMember Name="DN" DataType="BOOL" Value="0"/></Structure>'
                    ),
                )
            ),
        ),
        export=[CT("F2")],
    )
    e.case(
        "F2b_timer_prefix_pre_acc",
        env(
            "Tag",
            "F2b",
            ctag(
                tmr(
                    "F2b",
                    dec(
                        '<Structure DataType="TIMER"><DataValueMember Name="PRE" DataType="DINT" Value="1234"/><DataValueMember Name="ACC" DataType="DINT" Value="5"/></Structure>'
                    ),
                )
            ),
        ),
        export=[CT("F2b")],
    )
    simple = (
        '<StructureMember Name="a_nested_UDT" DataType="simple_udt">'
        + "".join(
            f'<DataValueMember Name="bool{i}" DataType="BOOL" Value="{i % 2}"/>'
            for i in range(1, 5)
        )
        + '<DataValueMember Name="Dint" DataType="DINT" Value="3"/><DataValueMember Name="real" DataType="DINT" Value="4"/><DataValueMember Name="lint" DataType="LINT" Value="99"/></StructureMember>'
    )
    gi = (
        '<StructureMember Name="an_aoi" DataType="GenericInput">'
        + "".join(
            f'<DataValueMember Name="{n}" DataType="{t}" Value="{v}"/>'
            for n, t, v in [
                ("EnableIn", "BOOL", 1),
                ("EnableOut", "BOOL", 0),
                ("physicalInput", "BOOL", 0),
                ("onDelay", "DINT", 11),
                ("offDelay", "DINT", 22),
                ("state", "BOOL", 0),
                ("risingEdge", "BOOL", 0),
                ("fallingEdge", "BOOL", 0),
                ("invert", "BOOL", 1),
                ("held", "BOOL", 0),
                ("holdTime", "DINT", 33),
            ]
        )
        + "</StructureMember>"
    )
    a_udt = (
        '<Structure DataType="A_UDT"><DataValueMember Name="a_Bool" DataType="BOOL" Value="1"/><DataValueMember Name="on_off_bool" DataType="BOOL" Value="0"/>'
        '<DataValueMember Name="a_sint" DataType="SINT" Value="-5"/><DataValueMember Name="a_sint_with_props" DataType="SINT" Value="6"/>'
        '<DataValueMember Name="a_real" DataType="REAL" Value="3.25"/><DataValueMember Name="another_bool" DataType="BOOL" Value="1"/>'
        '<DataValueMember Name="a_dint" DataType="DINT" Value="7"/>'
        + simple
        + gi
        + '<ArrayMember Name="an_array" DataType="REAL" Dimensions="4"><Element Index="[0]" Value="0.5"/><Element Index="[1]" Value="1.5"/><Element Index="[2]" Value="2.5"/><Element Index="[3]" Value="3.5"/></ArrayMember></Structure>'
    )
    e.case(
        "F3_udt_complete_noradix",
        env(
            "Tag",
            "F3",
            ctag(f'<Tag Use="Target" Name="F3" DataType="A_UDT">{dec(a_udt)}</Tag>'),
        ),
        export=[CT("F3")],
    )
    e.case(
        "F3b_udt_aoi_missing_hidden",
        env(
            "Tag",
            "F3b",
            ctag(
                f'<Tag Use="Target" Name="F3b" DataType="A_UDT">{dec(a_udt.replace(chr(60) + 'DataValueMember Name="EnableIn" DataType="BOOL" Value="1"/>', "").replace(chr(60) + 'DataValueMember Name="EnableOut" DataType="BOOL" Value="0"/>', ""))}</Tag>'
            ),
        ),
        export=[CT("F3b")],
    )
    arr = lambda n, els, extra="": (
        f'<Tag Use="Target" Name="{n}" DataType="DINT" Dimensions="5">{dec(f'<Array DataType="DINT" Dimensions="5"{extra}>{els}</Array>')}</Tag>'
    )  # noqa: E731
    e.case(
        "F4_array_full",
        env(
            "Tag",
            "F4",
            ctag(
                arr(
                    "F4",
                    "".join(
                        f'<Element Index="[{i}]" Value="{10 + i}"/>' for i in range(5)
                    ),
                )
            ),
        ),
        export=[CT("F4")],
    )
    e.case(
        "F4b_array_prefix",
        env(
            "Tag",
            "F4b",
            ctag(
                arr(
                    "F4b",
                    "".join(
                        f'<Element Index="[{i}]" Value="{10 + i}"/>' for i in range(2)
                    ),
                )
            ),
        ),
        export=[CT("F4b")],
    )
    e.case(
        "F5_array_noindex",
        env(
            "Tag",
            "F5",
            ctag(arr("F5", "".join(f'<Element Value="{10 + i}"/>' for i in range(5)))),
        ),
        export=[CT("F5")],
    )
    e.case(
        "F4c_array2d_full",
        env(
            "Tag",
            "F4c",
            ctag(
                '<Tag Use="Target" Name="F4c" DataType="INT" Dimensions="2 3">'
                + dec(
                    '<Array DataType="INT" Dimensions="2,3">'
                    + "".join(
                        f'<Element Index="[{i},{j}]" Value="{i * 10 + j}"/>'
                        for i in range(2)
                        for j in range(3)
                    )
                    + "</Array>"
                )
                + "</Tag>"
            ),
        ),
        export=[CT("F4c")],
    )
    e.case(
        "F6_l5k_udt_short",
        env(
            "Tag",
            "F6",
            ctag(
                f'<Tag Use="Target" Name="F6" DataType="A_UDT"><Data Format="L5K">{cd("[1,0,5]")}</Data></Tag>'
            ),
        ),
        export=[CT("F6")],
    )
    e.case(
        "F6b_l5k_timer_no_ctrl",
        env(
            "Tag",
            "F6b",
            ctag(
                f'<Tag Use="Target" Name="F6b" DataType="TIMER"><Data Format="L5K">{cd("[3000,0]")}</Data></Tag>'
            ),
        ),
        export=[CT("F6b")],
    )
    # header minimums
    for i, ra in enumerate(
        [
            'SchemaRevision="1.0" TargetType="Tag" ContainsContext="true"',
            'SchemaRevision="1.0" ContainsContext="true"',
            'SchemaRevision="1.0" TargetName="X" ContainsContext="true"',
            'SchemaRevision="1.0" TargetType="Tag"',
            'SchemaRevision="1.0" TargetType="Tag" TargetName="X" ContainsContext="true"',
        ]
    ):
        n = f"F7_{i}"
        e.case(
            f"F7_{i}_hdr",
            env("Tag", n, ctag(dint_tag(n, i)), root_attrs=ra),
            export=[CT(n)],
        )
    # import_target xpaths
    e.case(
        "F8a_tgt_tagxpath",
        env("Tag", "F8src", ctag('<Tag Use="Target" Name="F8src" DataType="DINT"/>')),
        op="import_target",
        xpath="Controller/Tags/Tag[@Name='F8a']",
        target="F8a",
        export=[CT("F8a")],
    )
    e.case(
        "F8b_tgt_tagcoll",
        env("Tag", "F8src", ctag('<Tag Use="Target" Name="F8src" DataType="DINT"/>')),
        op="import_target",
        xpath="Controller/Tags/Tag",
        target="F8b",
        export=[CT("F8b")],
    )
    e.case(
        "F8c_tgt_ctrl",
        env("Tag", "F8src", ctag('<Tag Use="Target" Name="F8src" DataType="DINT"/>')),
        op="import_target",
        xpath="Controller",
        target="F8c",
        export=[CT("F8c")],
    )
    # Use= semantics on existing tag (F1 has PRE=1234)
    e.case(
        "F9a_update_desc_nodata",
        env(
            "Tag",
            "F1",
            ctag(
                tmr(
                    "F1",
                    f"<Description>{cd('updated desc')}</Description>",
                    use='Use="Update" ',
                )
            ),
        ),
        export=[CT("F1")],
    )
    e.case(
        "F9b_overwrite_desc_nodata",
        env(
            "Tag",
            "F3",
            ctag(
                f'<Tag Use="Overwrite" Name="F3" DataType="A_UDT"><Description>{cd("ow desc")}</Description></Tag>'
            ),
        ),
        export=[CT("F3")],
    )
    e.case(
        "F9c_create_existing",
        env(
            "Tag",
            "F4",
            ctag('<Tag Use="Create" Name="F4" DataType="DINT" Dimensions="5"/>'),
        ),
        export=[CT("F4")],
    )
    e.case(
        "F9d_delete",
        env("Tag", "F4b", ctag('<Tag Use="Delete" Name="F4b"/>')),
        export=[CT("F4b")],
    )
    e.case(
        "F9e_update_change_type",
        env("Tag", "F5", ctag('<Tag Use="Update" Name="F5" DataType="REAL"/>')),
        export=[CT("F5")],
    )
    e.case(
        "F9f_target_desc_nodata_existing",
        env(
            "Tag",
            "F6",
            ctag(
                f'<Tag Use="Target" Name="F6" DataType="A_UDT"><Description>{cd("target desc")}</Description></Tag>'
            ),
        ),
        export=[CT("F6")],
    )
    e.case(
        "F10_no_controller",
        f'{DECL}<RSLogix5000Content SchemaRevision="1.0" TargetName="F10" TargetType="Tag" ContainsContext="false"><Tag Name="F10" DataType="DINT"/></RSLogix5000Content>',
        xpath="Controller/Tags",
        export=[CT("F10")],
    )
    e.write()


def udt(
    name, members, use='Use="Target" ', attrs='Family="NoFamily" Class="User"', desc=""
):
    d = f"<Description>{cd(desc)}</Description>" if desc else ""
    return f'<DataType {use}Name="{name}" {attrs}>{d}<Members>{members}</Members></DataType>'


def mem(name, dt, dim=0, extra="", desc=""):
    d = f"<Description>{cd(desc)}</Description>" if desc else ""
    return (
        f'<Member Name="{name}" DataType="{dt}" Dimension="{dim}"{extra}>{d}</Member>'
    )


def dts(xml):
    return f'<DataTypes Use="Context">{xml}</DataTypes>'


def DT(n):
    return f"Controller/DataTypes/DataType[@Name='{n}']"


def exp02():
    """UDT definitions."""
    e = Exp("exp02")
    e.export(
        "all_product_defined", "Controller/DataTypes/DataType[@Class='ProductDefined']"
    )
    e.case(
        "U01_bool_as_bool",
        env(
            "DataType",
            "U01",
            dts(
                udt(
                    "U01",
                    mem("Run", "BOOL")
                    + mem("Fault", "BOOL")
                    + mem("Speed", "REAL")
                    + mem("Done", "BOOL"),
                )
            ),
        ),
        export=[DT("U01")],
    )
    e.case(
        "U02_minimal_members",
        env(
            "DataType",
            "U02",
            dts(
                udt(
                    "U02",
                    '<Member Name="A" DataType="BOOL"/><Member Name="B" DataType="DINT"/><Member Name="C" DataType="REAL" Dimension="3"/>',
                )
            ),
        ),
        export=[DT("U02")],
    )
    e.case(
        "U03_custom_host_name",
        env(
            "DataType",
            "U03",
            dts(
                udt(
                    "U03",
                    mem("host0", "SINT", extra=' Hidden="true"')
                    + mem("a", "BIT", extra=' Target="host0" BitNumber="0"')
                    + mem("b", "BIT", extra=' Target="host0" BitNumber="1"')
                    + mem("x", "DINT"),
                )
            ),
        ),
        export=[DT("U03")],
    )
    e.case(
        "U04_missing_dep",
        env(
            "DataType", "U04", dts(udt("U04", mem("n", "NoSuchUDT") + mem("x", "DINT")))
        ),
        export=[DT("U04")],
    )
    e.case(
        "U05_dep_after_target",
        env(
            "DataType",
            "U05",
            dts(
                udt("U05", mem("n", "U05dep") + mem("x", "DINT"))
                + udt("U05dep", mem("y", "INT"), use='Use="Context" ')
            ),
        ),
        export=[DT("U05"), DT("U05dep")],
    )
    e.case(
        "U05b_dep_before_target",
        env(
            "DataType",
            "U05b",
            dts(
                udt("U05bdep", mem("y", "INT"), use='Use="Context" ')
                + udt("U05b", mem("n", "U05bdep") + mem("x", "DINT"))
            ),
        ),
        export=[DT("U05b"), DT("U05bdep")],
    )
    e.case(
        "U05c_dep_no_use",
        env(
            "DataType",
            "U05c",
            dts(
                udt("U05c", mem("n", "U05cdep") + mem("x", "DINT"))
                + udt("U05cdep", mem("y", "INT"), use="")
            ),
        ),
        export=[DT("U05c"), DT("U05cdep")],
    )
    e.case(
        "U08_bool_array32",
        env(
            "DataType",
            "U08",
            dts(udt("U08", mem("flags", "BOOL", 32) + mem("x", "DINT"))),
        ),
        export=[DT("U08")],
    )
    e.case(
        "U08b_bool_array10",
        env(
            "DataType",
            "U08b",
            dts(udt("U08b", mem("flags", "BOOL", 10) + mem("x", "DINT"))),
        ),
        export=[DT("U08b")],
    )
    e.case(
        "U09_ten_bools",
        env(
            "DataType",
            "U09",
            dts(
                udt(
                    "U09",
                    "".join(mem(f"b{i}", "BOOL") for i in range(10))
                    + mem("x", "DINT")
                    + mem("c", "BOOL"),
                )
            ),
        ),
        export=[DT("U09")],
    )
    e.case(
        "U11_aoi_member_and_timer",
        env(
            "DataType",
            "U11",
            dts(
                udt(
                    "U11",
                    mem("deb", "Debounce")
                    + mem("t", "TIMER")
                    + mem("s", "STRING")
                    + mem("arr", "TIMER", 4),
                )
            ),
        ),
        export=[DT("U11")],
    )
    e.case(
        "U12_descriptions",
        env(
            "DataType",
            "U12",
            dts(
                udt(
                    "U12",
                    mem("a", "DINT", desc="member a desc")
                    + mem(
                        "b",
                        "BOOL",
                        desc="bool b desc",
                        extra=' ExternalAccess="Read Only"',
                    ),
                    desc="the udt desc",
                )
            ),
        ),
        export=[DT("U12")],
    )
    e.case(
        "U13_string_family",
        env(
            "DataType",
            "U13",
            dts(
                udt(
                    "U13",
                    mem("LEN", "DINT")
                    + mem("DATA", "SINT", 20, extra=' Radix="ASCII"'),
                    attrs='Family="StringFamily" Class="User"',
                )
            ),
        ),
        export=[DT("U13")],
    )
    e.case(
        "U14_no_family_class",
        env("DataType", "U14", dts(udt("U14", mem("a", "DINT"), attrs=""))),
        export=[DT("U14")],
    )
    e.case(
        "U15_rename_target",
        env("DataType", "U15src", dts(udt("U15src", mem("a", "DINT")))),
        op="import_target",
        xpath="Controller",
        target="U15renamed",
        export=[DT("U15renamed")],
    )
    e.case(
        "U16_member_radix_hex",
        env(
            "DataType",
            "U16",
            dts(
                udt(
                    "U16",
                    mem("a", "DINT", extra=' Radix="Hex"')
                    + mem("r", "REAL", extra=' Radix="Exponential"'),
                )
            ),
        ),
        export=[DT("U16")],
    )
    # --- modifying a UDT in use ---
    e.case(
        "U20_create_utest",
        env(
            "DataType",
            "UTest",
            dts(udt("UTest", mem("a", "DINT") + mem("b", "BOOL") + mem("c", "REAL"))),
        ),
        export=[DT("UTest")],
    )
    e.case(
        "U21_tag_full",
        env(
            "Tag",
            "UTag",
            ctag(
                '<Tag Use="Target" Name="UTag" DataType="UTest">'
                + dec(
                    '<Structure DataType="UTest"><DataValueMember Name="a" DataType="DINT" Value="11"/><DataValueMember Name="b" DataType="BOOL" Value="1"/><DataValueMember Name="c" DataType="REAL" Value="2.5"/></Structure>'
                )
                + "</Tag>"
            ),
        ),
        export=[CT("UTag")],
    )
    e.case(
        "U21b_nested_user",
        env(
            "DataType",
            "UOuter",
            dts(udt("UOuter", mem("inner", "UTest") + mem("z", "DINT"))),
        ),
        export=[DT("UOuter")],
    )
    e.case(
        "U21c_outer_tag",
        env(
            "Tag",
            "UOutTag",
            ctag(
                '<Tag Use="Target" Name="UOutTag" DataType="UOuter">'
                + dec(
                    '<Structure DataType="UOuter"><StructureMember Name="inner" DataType="UTest"><DataValueMember Name="a" DataType="DINT" Value="21"/><DataValueMember Name="b" DataType="BOOL" Value="1"/><DataValueMember Name="c" DataType="REAL" Value="4.5"/></StructureMember><DataValueMember Name="z" DataType="DINT" Value="99"/></Structure>'
                )
                + "</Tag>"
            ),
        ),
        export=[CT("UOutTag")],
    )
    e.case(
        "U22_overwrite_reorder_add",
        env(
            "DataType",
            "UTest",
            dts(
                udt(
                    "UTest",
                    mem("c", "REAL")
                    + mem("new1", "INT")
                    + mem("a", "DINT")
                    + mem("b", "BOOL"),
                )
            ),
        ),
        export=[DT("UTest"), CT("UTag"), CT("UOutTag"), DT("UOuter")],
    )
    e.case(
        "U23_overwrite_change_type",
        env(
            "DataType",
            "UTest",
            dts(
                udt(
                    "UTest",
                    mem("c", "REAL")
                    + mem("new1", "INT")
                    + mem("a", "REAL")
                    + mem("b", "BOOL"),
                )
            ),
        ),
        export=[CT("UTag")],
    )
    e.case(
        "U24_overwrite_remove_member",
        env(
            "DataType", "UTest", dts(udt("UTest", mem("c", "REAL") + mem("b", "BOOL")))
        ),
        export=[CT("UTag"), CT("UOutTag")],
    )
    e.case(
        "U25_update_partial_members",
        env(
            "DataType",
            "UTest",
            dts(udt("UTest", mem("zz", "DINT"), use='Use="Update" ')),
        ),
        export=[DT("UTest"), CT("UTag")],
    )
    e.case(
        "U26_discard_existing",
        env("DataType", "UTest", dts(udt("UTest", mem("q", "DINT")))),
        coll="discard",
        export=[DT("UTest")],
    )
    e.case(
        "U27_overwrite_A_UDT_used_by_aoi_ctx",
        env(
            "DataType",
            "simple_udt",
            dts(
                udt(
                    "simple_udt",
                    "".join(mem(f"bool{i}", "BOOL") for i in range(1, 5))
                    + mem("Dint", "DINT")
                    + mem("real", "REAL")
                    + mem("lint", "LINT"),
                )
            ),
        ),
        export=[
            DT("simple_udt"),
            "Controller/Programs/Program[@Name='MainProgram']/Tags/Tag[@Name='a_simple_udt_instance']",
        ],
    )
    e.raw(id="build", op="build")
    e.write()


def split(src_fn, name, ids, keep):
    """Re-run src experiment with only (keep=True) or without (keep=False) the given case ids."""
    import builtins

    cap = {}
    orig = Exp.write
    Exp.write = lambda self: cap.setdefault("e", self)
    try:
        src_fn()
    finally:
        Exp.write = orig
    e = cap["e"]
    e.run, e.dir = name, HERE / name

    def match(st):
        sid = st["id"]
        return any(sid == i or sid.startswith(f"x_{i}_x") for i in ids)

    e.steps = [st for st in e.steps if match(st) == keep]
    used = {st.get("file") for st in e.steps}
    e.files = {k: v for k, v in e.files.items() if k in used}
    e.write()


DEP_IDS = [
    "U04_missing_dep",
    "U05_dep_after_target",
    "U05b_dep_before_target",
    "U05c_dep_no_use",
]


def exp02a():
    split(exp02, "exp02a", DEP_IDS, keep=False)


def exp02b():
    split(exp02, "exp02b", ["U05b_dep_before_target", "U05c_dep_no_use"], keep=True)


def exp02c():
    split(exp02, "exp02c", ["U05_dep_after_target"], keep=True)


def exp02d():
    split(exp02, "exp02d", ["U04_missing_dep"], keep=True)
    e = None


FIX = HERE.parent.parent / "tests" / "fixtures"
BLANK = {"create": {"rev": 37, "proc": "1756-L85E", "name": "Blank"}}
BLANK_ACD = "C:/Users/zwood/ldsdk/projects/base/blank.ACD"


def deps(*names):
    return (
        "<Dependencies>"
        + "".join(f'<Dependency Type="DataType" Name="{n}"/>' for n in names)
        + "</Dependencies>"
    )


def udt_d(name, members, depnames=(), use='Use="Target" '):
    return f'<DataType {use}Name="{name}" Family="NoFamily" Class="User"><Members>{members}</Members>{deps(*depnames) if depnames else ""}</DataType>'


def exp03a():
    e = Exp("exp03a", base=BLANK)
    e.raw(id="save_blank", op="save_as", name="blank.ACD")
    e.case(
        "V01_fixture_A_UDT_into_blank",
        FIX.joinpath("A_UDT_DataType.L5X").read_text(encoding="utf-8-sig"),
        export=[
            DT("A_UDT"),
            DT("simple_udt"),
            "Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name='GenericInput']",
        ],
    )
    e.raw(id="build", op="build")
    e.write()


def exp03b():
    e = Exp("exp03b")
    e.case(
        "V02_dep_after_with_depblock",
        env(
            "DataType",
            "V02",
            dts(
                udt_d("V02", mem("n", "V02dep") + mem("x", "DINT"), ["V02dep"])
                + udt_d("V02dep", mem("y", "INT"), use="")
            ),
        ),
        export=[DT("V02"), DT("V02dep")],
    )
    e.raw(id="build", op="build")
    e.write()


def exp03c():
    e = Exp("exp03c")
    e.case(
        "V03_dep_before_with_depblock",
        env(
            "DataType",
            "V03",
            dts(
                udt_d("V03dep", mem("y", "INT"), use="")
                + udt_d("V03", mem("n", "V03dep") + mem("x", "DINT"), ["V03dep"])
            ),
        ),
        export=[DT("V03"), DT("V03dep")],
    )
    e.raw(id="build", op="build")
    e.write()


def exp03d():
    e = Exp("exp03d")
    e.case(
        "V04a_dep_alone",
        env("DataType", "V04dep", dts(udt("V04dep", mem("y", "INT")))),
        export=[DT("V04dep")],
    )
    e.case(
        "V04b_target_alone",
        env("DataType", "V04", dts(udt("V04", mem("n", "V04dep") + mem("x", "DINT")))),
        export=[DT("V04")],
    )
    e.case(
        "V05_two_targets_indep",
        env(
            "DataType",
            "V05a",
            dts(udt("V05a", mem("y", "INT")) + udt("V05b", mem("z", "INT"))),
        ),
        export=[DT("V05a"), DT("V05b")],
    )
    e.raw(id="build", op="build")
    e.write()


def aois(xml):
    return f'<AddOnInstructionDefinitions Use="Context">{xml}</AddOnInstructionDefinitions>'


def aoi(
    name, params="", local="", routines="", attrs="", use='Use="Target" ', extra=""
):
    p = f"<Parameters>{params}</Parameters>" if params else ""
    l = f"<LocalTags>{local}</LocalTags>" if local else ""
    r = f"<Routines>{routines}</Routines>" if routines else ""
    return f'<AddOnInstructionDefinition {use}Name="{name}"{(" " + attrs) if attrs else ""}>{extra}{p}{l}{r}</AddOnInstructionDefinition>'


def par(name, dt, usage="Input", extra="", inner=""):
    return f'<Parameter Name="{name}" DataType="{dt}" Usage="{usage}"{extra}>{inner}</Parameter>'


def rll(name, *rungs):
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>'
        + "".join(
            f'<Rung Number="{i}" Type="N">'
            + (f"<Comment>{cd(c)}</Comment>" if c else "")
            + f"<Text>{cd(t)}</Text></Rung>"
            for i, (t, c) in enumerate(
                r if isinstance(r, tuple) else (r, None) for r in rungs
            )
        )
        + "</RLLContent></Routine>"
    )


def st(name, *lines):
    return (
        f'<Routine Name="{name}" Type="ST"><STContent>'
        + "".join(f'<Line Number="{i}">{cd(l)}</Line>' for i, l in enumerate(lines))
        + "</STContent></Routine>"
    )


def AOI(n):
    return f"Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name='{n}']"


def PT(prog, n):
    return f"Controller/Programs/Program[@Name='{prog}']/Tags/Tag[@Name='{n}']"


def exp04():
    """AOIs."""
    e = Exp("exp04")
    deb = FIX.joinpath("Debounce_AOI.L5X").read_text(encoding="utf-8-sig")
    e.case(
        "A01_fixture_renamed",
        deb.replace('Name="Debounce"', 'Name="Deb2"').replace(
            'TargetName="Debounce"', 'TargetName="Deb2"'
        ),
        export=[AOI("Deb2")],
    )
    e.case(
        "A02_minimal",
        env(
            "AddOnInstructionDefinition",
            "A02",
            aois(
                aoi(
                    "A02",
                    par("In1", "BOOL") + par("Out1", "BOOL", "Output"),
                    routines=rll("Logic", "XIC(In1)OTE(Out1);"),
                )
            ),
        ),
        export=[AOI("A02")],
    )
    e.case(
        "A03_no_usage_no_default_inout_local",
        env(
            "AddOnInstructionDefinition",
            "A03",
            aois(
                aoi(
                    "A03",
                    '<Parameter Name="Cfg" DataType="DINT"/>'
                    + par("Ref", "DINT", "InOut")
                    + par("RefT", "TIMER", "InOut")
                    + par("Out", "DINT", "Output"),
                    '<LocalTag Name="tmr" DataType="TIMER"/><LocalTag Name="cnt" DataType="DINT"/>',
                    rll("Logic", "TON(tmr,?,?);", "MOV(Cfg,Out)ADD(Ref,1,Ref);"),
                )
            ),
        ),
        export=[AOI("A03")],
    )
    e.case(
        "A04_st_logic",
        env(
            "AddOnInstructionDefinition",
            "A04",
            aois(
                aoi(
                    "A04",
                    par("A", "REAL") + par("B", "REAL") + par("Sum", "REAL", "Output"),
                    routines=st(
                        "Logic",
                        "Sum := A + B;",
                        "IF Sum > 10.0 THEN",
                        "  Sum := 10.0;",
                        "END_IF;",
                    ),
                )
            ),
        ),
        export=[AOI("A04")],
    )
    e.case(
        "A05_scan_modes",
        env(
            "AddOnInstructionDefinition",
            "A05",
            aois(
                aoi(
                    "A05",
                    par("Out1", "BOOL", "Output"),
                    routines=rll("Logic", "OTE(Out1);")
                    + rll("Prescan", "OTU(Out1);")
                    + rll("Postscan", "OTU(Out1);")
                    + rll("EnableInFalse", "OTU(Out1);"),
                    attrs='ExecutePrescan="true" ExecutePostscan="true" ExecuteEnableInFalse="true"',
                )
            ),
        ),
        export=[AOI("A05")],
    )
    e.case(
        "A05b_scan_routines_flags_false",
        env(
            "AddOnInstructionDefinition",
            "A05b",
            aois(
                aoi(
                    "A05b",
                    par("Out1", "BOOL", "Output"),
                    routines=rll("Logic", "OTE(Out1);") + rll("Prescan", "OTU(Out1);"),
                )
            ),
        ),
        export=[AOI("A05b")],
    )
    e.case(
        "A10_local_new_udt_with_dep",
        env(
            "AddOnInstructionDefinition",
            "A10",
            dts(udt("A10udt", mem("a", "DINT") + mem("b", "BOOL"), use=""))
            + aois(
                aoi(
                    "A10",
                    par("Out1", "BOOL", "Output"),
                    '<LocalTag Name="u" DataType="A10udt"/>',
                    rll("Logic", "XIC(u.b)OTE(Out1);"),
                    extra="",
                )
                .replace("<Routines>", "<Routines>")
                .replace(
                    "</AddOnInstructionDefinition>",
                    '<Dependencies><Dependency Type="DataType" Name="A10udt"/></Dependencies></AddOnInstructionDefinition>',
                )
            ),
        ),
        export=[AOI("A10"), DT("A10udt")],
    )
    e.case(
        "A12_param_flags",
        env(
            "AddOnInstructionDefinition",
            "A12",
            aois(
                aoi(
                    "A12",
                    par("Req", "DINT", extra=' Required="true" Visible="true"')
                    + par(
                        "Hid",
                        "DINT",
                        extra=' Required="false" Visible="false" ExternalAccess="Read Only"',
                        inner=f"<Description>{cd('hidden param')}</Description>",
                    )
                    + par("Out1", "DINT", "Output", extra=' Required="true"'),
                    routines=rll("Logic", "MOV(Req,Out1);"),
                    extra=f"<Description>{cd('aoi description')}</Description><RevisionNote>{cd('first')}</RevisionNote>",
                    attrs='Revision="2.5" Vendor="AIC"',
                )
            ),
        ),
        export=[AOI("A12")],
    )
    e.case(
        "A14_default_values",
        env(
            "AddOnInstructionDefinition",
            "A14",
            aois(
                aoi(
                    "A14",
                    par(
                        "onDelay",
                        "DINT",
                        inner='<DefaultData Format="Decorated"><DataValue DataType="DINT" Value="100"/></DefaultData>',
                    )
                    + par("Out1", "DINT", "Output"),
                    '<LocalTag Name="t" DataType="TIMER"><DefaultData Format="Decorated"><Structure DataType="TIMER"><DataValueMember Name="PRE" DataType="DINT" Value="777"/><DataValueMember Name="ACC" DataType="DINT" Value="0"/><DataValueMember Name="EN" DataType="BOOL" Value="0"/><DataValueMember Name="TT" DataType="BOOL" Value="0"/><DataValueMember Name="DN" DataType="BOOL" Value="0"/></Structure></DefaultData></LocalTag>',
                    rll("Logic", "MOV(onDelay,Out1);"),
                )
            ),
        ),
        export=[AOI("A14")],
    )
    e.case(
        "A14b_tag_of_A14_nodata",
        env("Tag", "A14tag", ctag('<Tag Use="Target" Name="A14tag" DataType="A14"/>')),
        export=[CT("A14tag")],
    )
    # ---- modifying existing AOIs in use ----
    e.export("pre_TestInput", PT("AnotherProgram", "TestInput"))
    gi_mod = FIX.joinpath("A_UDT_DataType.L5X").read_text(encoding="utf-8-sig")
    e.case(
        "A06_overwrite_debounce_logic",
        deb.replace('Revision="1.2"', 'Revision="1.3"').replace(
            "NOP();]]", "NOP()NOP();]]"
        ),
        export=[AOI("Debounce"), PT("AnotherProgram", "TestInput")],
    )
    e.case(
        "A13_overwrite_lower_rev",
        deb.replace('Revision="1.2"', 'Revision="1.0"'),
        export=[AOI("Debounce")],
    )
    e.case(
        "A07_overwrite_add_param_GenericInput",
        env(
            "AddOnInstructionDefinition",
            "GenericInput",
            aois(
                aoi(
                    "GenericInput",
                    par("physicalInput", "BOOL")
                    + par("newParam", "DINT")
                    + par("onDelay", "DINT")
                    + par("offDelay", "DINT")
                    + par("state", "BOOL", "Output")
                    + par("holdTime", "DINT"),
                    '<LocalTag Name="deb" DataType="Debounce"/>',
                    rll("Logic", "XIC(physicalInput)OTE(state);"),
                    attrs='Revision="2.0"',
                )
            ),
        ),
        export=[AOI("GenericInput"), PT("AnotherProgram", "TestInput"), DT("A_UDT")],
    )
    e.case(
        "A11_update_revnote_only",
        env(
            "AddOnInstructionDefinition",
            "Debounce",
            aois(
                f'<AddOnInstructionDefinition Use="Update" Name="Debounce" Revision="1.4"><RevisionNote>{cd("update via Use=Update")}</RevisionNote></AddOnInstructionDefinition>'
            ),
        ),
        export=[AOI("Debounce")],
    )
    e.raw(id="build", op="build")
    e.write()


def exp04x():
    """AOI errors (separate: they break build)."""
    e = Exp("exp04x")
    e.case(
        "A08_undefined_tag_in_logic",
        env(
            "AddOnInstructionDefinition",
            "A08",
            aois(
                aoi(
                    "A08",
                    par("Out1", "BOOL", "Output"),
                    routines=rll("Logic", "XIC(nope)OTE(Out1);"),
                )
            ),
        ),
        export=[AOI("A08")],
    )
    e.case(
        "A09_missing_udt_local",
        env(
            "AddOnInstructionDefinition",
            "A09",
            aois(
                aoi(
                    "A09",
                    par("Out1", "BOOL", "Output"),
                    '<LocalTag Name="u" DataType="NoSuchUDT"/>',
                    rll("Logic", "OTE(Out1);"),
                )
            ),
        ),
        export=[AOI("A09")],
    )
    e.case(
        "A15_no_logic_routine",
        env(
            "AddOnInstructionDefinition",
            "A15",
            aois(aoi("A15", par("Out1", "BOOL", "Output"))),
        ),
        export=[AOI("A15")],
    )
    e.case(
        "A16_bad_syntax",
        env(
            "AddOnInstructionDefinition",
            "A16",
            aois(
                aoi(
                    "A16",
                    par("Out1", "BOOL", "Output"),
                    routines=rll("Logic", "XIC(Out1 OTE(Out1);"),
                )
            ),
        ),
        export=[AOI("A16")],
    )
    e.raw(id="build", op="build")
    e.write()


def prog(
    name,
    tags="",
    routines="",
    attrs='MainRoutineName="MainRoutine"',
    use='Use="Target" ',
):
    return f'<Program {use}Name="{name}" {attrs}><Tags>{tags}</Tags><Routines>{routines}</Routines></Program>'


def progs(xml):
    return f'<Programs Use="Context">{xml}</Programs>'


def PR(n):
    return f"Controller/Programs/Program[@Name='{n}']"


def RT(p, r):
    return f"{PR(p)}/Routines/Routine[@Name='{r}']"


def rung_file(prog_name, routine, rungs_xml):
    return env(
        "Rung",
        "x",
        progs(
            f'<Program Use="Context" Name="{prog_name}"><Routines Use="Context"><Routine Use="Context" Name="{routine}"><RLLContent Use="Context">{rungs_xml}</RLLContent></Routine></Routines></Program>'
        ),
    )


def rung(text, comment=None, n=0, use='Use="Target" '):
    c = f"<Comment>{cd(comment)}</Comment>" if comment else ""
    return f'<Rung {use}Number="{n}" Type="N">{c}<Text>{cd(text)}</Text></Rung>'


def exp05():
    """Programs / routines / rungs (valid)."""
    e = Exp("exp05")
    tags = '<Tag Name="t1" DataType="TIMER"/><Tag Name="cnt" DataType="DINT"/><Tag Name="go" DataType="BOOL"/><Tag Name="d" DataType="Debounce"/>'
    main = rll(
        "MainRoutine",
        ("XIC(go)TON(t1,1000,0);", "start timer"),
        "XIC(t1.DN)ADD(cnt,1,cnt)RES(t1);",
        "JSR(StRoutine,0);",
        "Debounce(d,500,500);",
    )
    e.case(
        "R01_new_program",
        env(
            "Program",
            "GenProg",
            progs(
                prog(
                    "GenProg",
                    tags,
                    main
                    + st(
                        "StRoutine",
                        "cnt := cnt + 1;",
                        "IF cnt > 100 THEN cnt := 0; END_IF;",
                    ),
                )
            ),
        ),
        export=[PR("GenProg"), "Controller/Tasks/Task[@Name='MainTask']"],
    )
    e.case(
        "R01b_target_into_task",
        env(
            "Program",
            "GenProg",
            progs(prog("GenProg", tags, main + st("StRoutine", "cnt := 0;"))),
        ),
        op="import_target",
        xpath="Controller/Tasks/Task[@Name='MainTask']",
        target="GenProg2",
        export=[PR("GenProg2"), "Controller/Tasks/Task[@Name='MainTask']"],
    )
    e.case(
        "R01c_minimal_program",
        env(
            "Program",
            "MinProg",
            progs(
                '<Program Use="Target" Name="MinProg"><Routines>'
                + rll("R", "NOP();")
                + "</Routines></Program>"
            ),
        ),
        export=[PR("MinProg")],
    )
    e.case(
        "R02_rungs_insert_top",
        rung_file("GenProg", "MainRoutine", rung("XIC(go)OTE(go);", "inserted rung")),
        op="import_rungs",
        xpath=RT("GenProg", "MainRoutine"),
        pos=0,
        replace=0,
        export=[RT("GenProg", "MainRoutine")],
    )
    e.case(
        "R02b_rungs_replace",
        rung_file(
            "GenProg",
            "MainRoutine",
            rung("XIO(go)OTE(go);", "replaced rung 1") + rung("NOP();", n=1),
        ),
        op="import_rungs",
        xpath=RT("GenProg", "MainRoutine"),
        pos=1,
        replace=1,
        export=[RT("GenProg", "MainRoutine")],
    )
    e.case(
        "R02c_rungs_append_end",
        rung_file("GenProg", "MainRoutine", rung("NOP();", "appended")),
        op="import_rungs",
        xpath=RT("GenProg", "MainRoutine"),
        pos=99,
        replace=0,
        export=[RT("GenProg", "MainRoutine")],
    )
    e.case(
        "R02d_rung_via_generic_import",
        rung_file("GenProg", "MainRoutine", rung("NOP();", "generic import")),
        export=[RT("GenProg", "MainRoutine")],
    )
    e.case(
        "R02e_rung_new_tag_ctx",
        env(
            "Rung",
            "x",
            progs(
                '<Program Use="Context" Name="GenProg"><Tags Use="Context"><Tag Name="newTag" DataType="DINT"/></Tags><Routines Use="Context"><Routine Use="Context" Name="MainRoutine"><RLLContent Use="Context">'
                + rung("MOV(5,newTag);", "uses new tag")
                + "</RLLContent></Routine></Routines></Program>"
            ),
        ),
        op="import_rungs",
        xpath=RT("GenProg", "MainRoutine"),
        pos=0,
        replace=0,
        export=[RT("GenProg", "MainRoutine"), PT("GenProg", "newTag")],
    )
    e.case(
        "R06_routine_into_existing",
        env(
            "Routine",
            "NewR",
            progs(
                '<Program Use="Context" Name="GenProg"><Routines Use="Context">'
                + rll("NewR", "NOP();").replace("<Routine ", '<Routine Use="Target" ')
                + "</Routines></Program>"
            ),
        ),
        export=[RT("GenProg", "NewR")],
    )
    e.case(
        "R06b_routine_target_rename",
        env(
            "Routine",
            "NewR",
            progs(
                '<Program Use="Context" Name="GenProg"><Routines Use="Context">'
                + rll("NewR", "NOP();").replace("<Routine ", '<Routine Use="Target" ')
                + "</Routines></Program>"
            ),
        ),
        op="import_target",
        xpath=PR("PeriodicProgram"),
        target="CopiedR",
        export=[RT("PeriodicProgram", "CopiedR")],
    )
    e.export("pre_periodic", PR("PeriodicProgram"))
    e.raw(
        id="set_test_dint",
        op="set",
        xpath=PT("PeriodicProgram", "test_dint"),
        type="dint",
        value=4321,
    )
    e.case(
        "R07_overwrite_program",
        env(
            "Program",
            "PeriodicProgram",
            progs(
                prog(
                    "PeriodicProgram",
                    '<Tag Name="test_bool" DataType="BOOL"/><Tag Name="test_dint" DataType="DINT"/><Tag Name="test_int" DataType="INT"/><Tag Name="added" DataType="REAL"/>',
                    rll("main", "XIC(test_bool)MOV(test_dint,test_int);", "NOP();"),
                    attrs='MainRoutineName="main"',
                )
            ),
        ),
        export=[PR("PeriodicProgram"), "Controller/Tasks/Task[@Name='PeriodicTask']"],
    )
    e.raw(
        id="get_test_dint",
        op="get",
        xpath=PT("PeriodicProgram", "test_dint"),
        type="dint",
    )
    e.case(
        "R08_update_program_add_routine",
        env(
            "Program",
            "PeriodicProgram",
            progs(
                '<Program Use="Update" Name="PeriodicProgram"><Routines>'
                + rll("extra", "NOP();")
                + "</Routines></Program>"
            ),
        ),
        export=[PR("PeriodicProgram")],
    )
    e.case(
        "R09_whitespace_rung",
        rung_file(
            "GenProg", "MainRoutine", rung("XIC(go)\n   OTE(go)  ;", "whitespace")
        ),
        op="import_rungs",
        xpath=RT("GenProg", "MainRoutine"),
        pos=0,
        replace=0,
        export=[RT("GenProg", "MainRoutine")],
    )
    e.raw(id="build", op="build")
    e.raw(id="save", op="save_as", name="final.L5X")
    e.write()


def exp05x():
    """Logic errors."""
    e = Exp("exp05x")
    e.case(
        "X01_rung_undefined_tag",
        rung_file(
            "MainProgram", "MainRoutine", rung("XIC(undefinedTag)OTE(alsoUndefined);")
        ),
        op="import_rungs",
        xpath=RT("MainProgram", "MainRoutine"),
        pos=0,
        replace=0,
        export=[RT("MainProgram", "MainRoutine")],
    )
    e.case(
        "X02_rung_syntax",
        rung_file("MainProgram", "MainRoutine", rung("XIC(a_bool OTE(a_bool);")),
        op="import_rungs",
        xpath=RT("MainProgram", "MainRoutine"),
        pos=0,
        replace=0,
        export=[RT("MainProgram", "MainRoutine")],
    )
    e.case(
        "X03_rung_bad_instruction",
        rung_file("MainProgram", "MainRoutine", rung("FOO(a_bool);")),
        op="import_rungs",
        xpath=RT("MainProgram", "MainRoutine"),
        pos=0,
        replace=0,
    )
    e.case(
        "X04_st_syntax",
        env(
            "Program",
            "BadSt",
            progs(
                prog(
                    "BadSt",
                    '<Tag Name="x" DataType="DINT"/>',
                    st("MainRoutine", "x := ;", "IF THEN"),
                )
            ),
        ),
        export=[PR("BadSt")],
    )
    e.case(
        "X05_program_undefined_tag",
        env(
            "Program",
            "BadTags",
            progs(
                prog("BadTags", "", rll("MainRoutine", "XIC(missing)OTE(missing2);"))
            ),
        ),
        export=[PR("BadTags")],
    )
    e.case(
        "X06_wrong_operand_type",
        rung_file("MainProgram", "MainRoutine", rung("TON(a_bool,100,0);")),
        op="import_rungs",
        xpath=RT("MainProgram", "MainRoutine"),
        pos=0,
        replace=0,
    )
    e.raw(id="build", op="build")
    e.write()


def exp03e():
    """Persistence: BOOL-as-BOOL UDT + tag data survive save/reopen?"""
    e = Exp("exp03e")
    e.case(
        "P01_udt",
        env(
            "DataType",
            "P01",
            dts(
                udt(
                    "P01",
                    mem("Run", "BOOL")
                    + mem("Fault", "BOOL")
                    + mem("Speed", "REAL")
                    + mem("Done", "BOOL"),
                )
            ),
        ),
    )
    e.case(
        "P02_tag",
        env(
            "Tag",
            "P02",
            ctag(
                '<Tag Use="Target" Name="P02" DataType="P01">'
                + dec(
                    '<Structure DataType="P01"><DataValueMember Name="Run" DataType="BOOL" Value="1"/><DataValueMember Name="Fault" DataType="BOOL" Value="0"/><DataValueMember Name="Speed" DataType="REAL" Value="1.25"/><DataValueMember Name="Done" DataType="BOOL" Value="1"/></Structure>'
                )
                + "</Tag>"
            ),
        ),
    )
    e.raw(id="save", op="save_as", name="persist.ACD")
    e.write()


def exp03f():
    e = Exp("exp03f", base="C:/Users/zwood/ldsdk/out/exp03e/persist.ACD")
    e.export("P01", DT("P01"))
    e.export("P02", CT("P02"))
    e.raw(id="get_speed", op="get", xpath=CT("P02"), type="dint")
    e.write()


def exp06():
    e = Exp("exp06")
    # 1. BOOL packing: plain BOOL vs hidden-host form, compare raw tag sizes
    bools = "".join(mem(f"b{i}", "BOOL") for i in range(8))
    e.case(
        "K01_udt_bool_plain",
        env("DataType", "K01", dts(udt("K01", bools + mem("x", "DINT")))),
    )
    host = mem("ZZZZZZZZZZK020", "SINT", extra=' Hidden="true"') + "".join(
        mem(f"b{i}", "BIT", extra=f' Target="ZZZZZZZZZZK020" BitNumber="{i}"')
        for i in range(8)
    )
    e.case(
        "K02_udt_bool_host",
        env("DataType", "K02", dts(udt("K02", host + mem("x", "DINT")))),
    )
    e.case(
        "K03_tags",
        env(
            "Tag",
            "K01t",
            ctag(
                '<Tag Use="Target" Name="K01t" DataType="K01"/><Tag Use="Target" Name="K02t" DataType="K02"/><Tag Use="Target" Name="Ttimer" DataType="TIMER"/>'
            ),
        ),
    )
    e.raw(id="raw_K01t", op="get", xpath=CT("K01t"), type="raw")
    e.raw(id="raw_K02t", op="get", xpath=CT("K02t"), type="raw")
    e.raw(
        id="raw_A_UDT", op="get", xpath=PT("MainProgram", "a_udt_instance"), type="raw"
    )
    e.raw(id="raw_timer", op="get", xpath=CT("Ttimer"), type="raw")
    e.export("K01", DT("K01"))
    # 2. scheduling programs
    p1 = prog("SchedA", "", rll("MainRoutine", "NOP();"))
    e.case(
        "S01_program_plus_task_update",
        env(
            "Program",
            "SchedA",
            progs(p1)
            + '<Tasks Use="Context"><Task Use="Update" Name="MainTask"><ScheduledPrograms><ScheduledProgram Name="SchedA"/></ScheduledPrograms></Task></Tasks>',
        ),
        export=["Controller/Tasks/Task[@Name='MainTask']"],
    )
    e.case(
        "S02_target_into_task_fixture",
        FIX.joinpath("MainProgram_Program.L5X").read_text(encoding="utf-8-sig"),
        op="import_target",
        xpath="Controller/Tasks/Task[@Name='PeriodicTask']",
        target="MainProgramCopy",
        export=["Controller/Tasks/Task[@Name='PeriodicTask']", PR("MainProgramCopy")],
    )
    e.case(
        "S03_target_into_task_minimal_noctx",
        env(
            "Program", "SchedC", progs(prog("SchedC", "", rll("MainRoutine", "NOP();")))
        ),
        op="import_target",
        xpath="Controller/Tasks/Task[@Name='PeriodicTask']",
        target="SchedC",
        export=["Controller/Tasks/Task[@Name='PeriodicTask']"],
    )
    e.case(
        "S04_target_programs_coll",
        env(
            "Program", "SchedD", progs(prog("SchedD", "", rll("MainRoutine", "NOP();")))
        ),
        op="import_target",
        xpath="Controller/Programs",
        target="SchedD2",
        export=[PR("SchedD2")],
    )
    # 3. Program Use=Update preserves values?
    e.raw(
        id="set_test_dint",
        op="set",
        xpath=PT("PeriodicProgram", "test_dint"),
        type="dint",
        value=4321,
    )
    e.case(
        "S05_program_update_rung",
        env(
            "Program",
            "PeriodicProgram",
            progs(
                '<Program Use="Update" Name="PeriodicProgram"><Routines><Routine Use="Overwrite" Name="main" Type="RLL"><RLLContent><Rung Number="0" Type="N"><Text><![CDATA[XIC(test_bool)MOV(test_dint,test_int);]]></Text></Rung></RLLContent></Routine></Routines></Program>'
            ),
        ),
        export=[PR("PeriodicProgram")],
    )
    e.raw(
        id="get_test_dint_after_update",
        op="get",
        xpath=PT("PeriodicProgram", "test_dint"),
        type="dint",
    )
    e.case(
        "S06_program_overwrite_with_tag_nodata",
        env(
            "Program",
            "PeriodicProgram",
            progs(
                prog(
                    "PeriodicProgram",
                    '<Tag Name="test_bool" DataType="BOOL"/><Tag Use="Update" Name="test_dint" DataType="DINT"/><Tag Name="test_int" DataType="INT"/>',
                    rll("main", "NOP();"),
                    attrs='MainRoutineName="main"',
                )
            ),
        ),
    )
    e.raw(
        id="get_test_dint_after_overwrite_tagupdate",
        op="get",
        xpath=PT("PeriodicProgram", "test_dint"),
        type="dint",
    )
    # 4. Tag Use=Update with full data keeps description?
    e.case(
        "S07a_tag_with_desc",
        env(
            "Tag",
            "S07",
            ctag(
                f'<Tag Use="Target" Name="S07" DataType="TIMER"><Description>{cd("keep me")}</Description><Comments><Comment Operand=".PRE">{cd("pre cmt")}</Comment></Comments></Tag>'
            ),
        ),
    )
    e.case(
        "S07b_tag_update_data_only",
        env(
            "Tag",
            "S07",
            ctag(
                '<Tag Use="Update" Name="S07" DataType="TIMER">'
                + dec(TMR_FULL.format(pre=999, acc=1))
                + "</Tag>"
            ),
        ),
        export=[CT("S07")],
    )
    # 5. TON literal vs explicit tag data
    e.case(
        "S08_ton_literal_vs_data",
        env(
            "Program",
            "TonP",
            progs(
                prog(
                    "TonP",
                    '<Tag Name="t" DataType="TIMER">'
                    + dec(TMR_FULL.format(pre=5, acc=0))
                    + "</Tag>",
                    rll("MainRoutine", "TON(t,3000,0);"),
                )
            ),
        ),
        export=[PT("TonP", "t")],
    )
    e.case(
        "S09_ton_literal_existing_tag",
        rung_file("TonP", "MainRoutine", rung("TON(t,7777,0);")),
        op="import_rungs",
        xpath=RT("TonP", "MainRoutine"),
        pos=0,
        replace=0,
        export=[PT("TonP", "t")],
    )
    e.raw(id="build", op="build")
    e.write()


def _rt(name, mutate=None):
    import importlib.util

    spec = importlib.util.spec_from_file_location("rt_writer", HERE / "rt_writer.py")
    rw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rw)
    proj = rw.load(str(FIX / "example.L5X"))
    if mutate:
        mutate(proj)
    d = HERE / name
    d.mkdir(exist_ok=True)
    for f in d.glob("*.L5X"):
        f.unlink()
    rw.write(proj, d / "rt.L5X")
    return proj


def exp07a():
    """Full project: unmodified load -> write round trip."""
    _rt("exp07a")
    e = Exp("exp07a", base="C:/Users/zwood/ldsdk/projects/exp07a/rt.L5X")
    e.files = {"rt.L5X": (HERE / "exp07a" / "rt.L5X").read_bytes()}
    e.raw(id="build", op="build")
    e.raw(id="save", op="save_as", name="rt_resaved.L5X")
    e.write()


def exp07b():
    """Full project: edits via ElementTree (rung text, tag value, new tag, UDT member, AOI rev)."""
    import xml.etree.ElementTree as ET

    def mutate(p):
        root = p._root
        c = root.find("Controller")
        # rung text in MainProgram/MainRoutine rung 0
        r = c.find(
            "Programs/Program[@Name='PeriodicProgram']/Routines/Routine[@Name='main']/RLLContent/Rung/Text"
        )
        r[0].text = "XIC(test_bool)MOV(test_dint,test_int);"
        # tag value: test_dint = 1234 (both L5K and Decorated)
        t = c.find(
            "Programs/Program[@Name='PeriodicProgram']/Tags/Tag[@Name='test_dint']"
        )
        for d in t.findall("Data"):
            if d.get("Format") == "L5K":
                d[0].text = "1234"
            else:
                d.find("DataValue").set("Value", "1234")
        # new controller tag, no data
        tags = c.find("Tags")
        ET.SubElement(tags, "Tag", Name="rt_new_tag", TagType="Base", DataType="TIMER")
        # add a BOOL member at end of simple_udt  (tags of this type have data that now lacks the member!)
        m = c.find("DataTypes/DataType[@Name='simple_udt']/Members")
        ET.SubElement(
            m,
            "Member",
            Name="added_member",
            DataType="DINT",
            Dimension="0",
            Radix="Decimal",
            Hidden="false",
            ExternalAccess="Read/Write",
        )
        # AOI revision bump
        c.find(
            "AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name='Debounce']"
        ).set("Revision", "1.9")

    _rt("exp07b", mutate)
    e = Exp("exp07b", base="C:/Users/zwood/ldsdk/projects/exp07b/rt.L5X")
    e.files = {"rt.L5X": (HERE / "exp07b" / "rt.L5X").read_bytes()}
    e.raw(
        id="get_test_dint",
        op="get",
        xpath=PT("PeriodicProgram", "test_dint"),
        type="dint",
    )
    e.export("periodic", PR("PeriodicProgram"))
    e.export("new_tag", CT("rt_new_tag"))
    e.export("simple_udt", DT("simple_udt"))
    e.export("simple_inst", PT("MainProgram", "a_simple_udt_instance"))
    e.export("deb", AOI("Debounce"))
    e.raw(id="build", op="build")
    e.write()


def exp08():
    """Bisect build errors on a blank project: one program per rung, build after each."""
    e = Exp("exp08", base=BLANK_ACD)
    tags = '<Tag Name="b" DataType="BOOL"/><Tag Name="c" DataType="BOOL"/><Tag Name="d" DataType="DINT"/><Tag Name="i" DataType="INT"/><Tag Name="t" DataType="TIMER"/>'
    cases = [
        ("B1_ote", "XIC(b)OTE(c);"),
        ("B2_mov", "XIC(b)MOV(d,i);"),
        ("B3_move", "XIC(b)MOVE(d,i);"),
        ("B4_mov_only", "MOV(d,i);"),
        ("B5_ton_q", "TON(t,?,?);"),
        ("B6_add", "ADD(d,1,d);"),
        ("B7_branch", "[XIC(b) ,XIO(c) ]OTE(c);"),
        ("B8_nop", "NOP();"),
    ]
    for cid, txt in cases:
        name = "P_" + cid
        e.case(
            cid,
            env("Program", name, progs(prog(name, tags, rll("MainRoutine", txt)))),
            export=[RT(name, "MainRoutine")],
        )
        e.raw(id=f"build_{cid}", op="build")
        e.case(
            f"del_{cid}",
            env("Program", name, progs(f'<Program Use="Delete" Name="{name}"/>')),
        )
    e.write()


def exp09():
    """Value formatting per radix: import decimal values, export to see Studio's canonical text."""
    e = Exp("exp09", base=BLANK_ACD)
    rows = []
    ints = [
        ("SINT", [0, 65, -1, 127, -128]),
        ("INT", [0, 255, -1]),
        ("DINT", [0, 255, -1, 2147483647, -2147483648]),
        ("LINT", [0, 255, -1]),
        ("USINT", [0, 200]),
        ("UINT", [0, 65535]),
        ("UDINT", [0, 4294967295]),
        ("ULINT", [0, 18446744073709551615]),
    ]
    for dt, vals in ints:
        for radix in ["Decimal", "Hex", "Octal", "Binary", "ASCII"]:
            for v in vals:
                rows.append((dt, radix, str(v)))
    for dt in ["REAL", "LREAL"]:
        for radix in ["Float", "Exponential"]:
            for v in [
                "0.0",
                "0.1",
                "1.5",
                "-2.25",
                "1234567.0",
                "1e20",
                "1e-10",
                "3.4028235e38",
                "16777217.0",
                "123456789.123456789",
            ]:
                rows.append((dt, radix, v))
    tags = []
    for i, (dt, radix, v) in enumerate(rows):
        n = f"v{i:03d}_{dt}_{radix}"
        tags.append(
            f'<Tag Name="{n}" DataType="{dt}" Radix="{radix}"><Data Format="Decorated"><DataValue DataType="{dt}" Radix="{radix}" Value="{v}"/></Data></Tag>'
        )
    e.case("V_values", env("Tag", "x", ctag("".join(tags))))
    e.export("all_tags", "Controller/Tags/Tag")
    e.write()
    (HERE / "exp09" / "rows.json").write_text(json.dumps(rows))


def _py_l5x():
    sys.path.insert(0, str(HERE.parent.parent))
    import py_l5x
    import py_l5x.writer  # noqa: F401  (submodule, imported lazily by the package)

    return py_l5x


# Expected values after the exp10 edits: (export name, xpath, regex that must match the export)
EXP10_EDITS = []


def exp10_edit(p):
    """Apply the exp10 edits to a loaded example project via the public API."""
    mp = p.programs["MainProgram"]
    mp.tags["a_timer"].members["PRE"].value = 4321
    mp.tags["a_dint"].value = -77
    mp.tags["a_dint"].description = "edited dint description"
    mp.tags["a_real"].value = 2.75
    mp.tags["a_bool"].value = True
    u = mp.tags["a_udt_instance"]
    u.members["a_real"].value = 9.5
    u.members["a_Bool"].value = True
    u.members["a_nested_UDT"].members["lint"].value = 123456789
    mp.tags["a_2d_array"][1, 2].value = 42
    mp.tags["a_string"].value = "hello $ 'world'"
    mp.tags["a_custom_string"].value = "ABC"
    p.controller_tags["ALLOWABLE_ALARMS"][3].value = "SRVO-999"
    mp.tags["sequence"].members["startupStep"].value = 1234
    aoi = p.aois["Debounce"]
    aoi.parameters["onDelay"].value = 250
    aoi.description = "edited aoi description"
    r = p.programs["PeriodicProgram"].routines["main"].rungs[0]
    r.comment = "edited rung comment"
    p.data_types["simple_udt"].description = "edited udt description"


EXP10_CHECKS = [
    ("a_timer", "MainProgram", "a_timer", r'Name="PRE"[^>]*Value="4321"'),
    ("a_dint", "MainProgram", "a_dint", r'Value="-77".*|edited dint description'),
    ("a_real", "MainProgram", "a_real", r'Value="2.75"'),
    ("a_bool", "MainProgram", "a_bool", r'Value="1"'),
    ("a_udt_instance", "MainProgram", "a_udt_instance", r'Name="a_Bool"[^>]*Value="1"'),
    ("a_2d_array", "MainProgram", "a_2d_array", r'Index="\[1,2\]" Value="42"'),
    ("a_string", "MainProgram", "a_string", r"hello \$\$ \$'world\$'"),
    ("a_custom_string", "MainProgram", "a_custom_string", r"'ABC'"),
    ("ALLOWABLE_ALARMS", None, "ALLOWABLE_ALARMS", r"'SRVO-999'"),
    ("sequence", "MainProgram", "sequence", r'Name="startupStep"[^>]*Value="1234"'),
]


def exp10():
    """Edits through the py_l5x API: full project opened in Studio, then component imports."""
    py_l5x = _py_l5x()
    p = py_l5x.load(str(FIX / "example.L5X"))
    exp10_edit(p)
    d = HERE / "exp10"
    d.mkdir(exist_ok=True)
    p.write(d / "edited.L5X")
    e = Exp("exp10", base="C:/Users/zwood/ldsdk/projects/exp10/edited.L5X")
    e.files = {"edited.L5X": (d / "edited.L5X").read_bytes()}
    for name, prog_name, tag, _ in EXP10_CHECKS:
        e.export(name, PT(prog_name, tag) if prog_name else CT(tag))
    e.export("debounce", AOI("Debounce"))
    e.export("periodic_main", RT("PeriodicProgram", "main"))
    e.export("simple_udt", DT("simple_udt"))
    e.raw(id="build", op="build")
    # component round trips: load fixture, edit, write, import into blank-ish base
    comp = py_l5x.load(str(FIX / "A_UDT_DataType.L5X"))
    comp.data_types["A_UDT"].description = "component edit"
    e.files["c_udt.L5X"] = py_l5x.writer.to_bytes(comp.root)
    e.steps.append(
        {
            "id": "C1_udt_component",
            "op": "import",
            "file": "c_udt.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    e.export("c_udt", DT("A_UDT"))
    deb = py_l5x.load(str(FIX / "Debounce_AOI.L5X"))
    deb.aois["Debounce"].parameters["offDelay"].value = 999
    deb.aois["Debounce"].routines["Logic"].rungs[1].comment = "component rung comment"
    e.files["c_aoi.L5X"] = py_l5x.writer.to_bytes(deb.root)
    e.steps.append(
        {
            "id": "C2_aoi_component",
            "op": "import",
            "file": "c_aoi.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    e.export("c_aoi", AOI("Debounce"))
    e.raw(id="build2", op="build")
    e.write()


def exp11():
    """How Studio canonicalizes string escape sequences."""
    e = Exp("exp11", base=BLANK_ACD)
    lits = [
        "'a$Lb'",
        "'a$lb'",
        "'a$Nb'",
        "'a$Rb'",
        "'a$Tb'",
        "'a$Pb'",
        "'a$0Ab'",
        "'a$0ab'",
        "'a$09b'",
        "'a$7Eb'",
        "'a$E9b'",
        "'$$$''",
        "'a\"b'",
        "'\u00e9'",
        "'tab\there'",
    ]
    tags = []
    lens = [3] * 11 + [2, 3, 1, 8]
    for i, lit in enumerate(lits):
        n = f"s{i:02d}"
        raw = lit.replace("\\t", "\t")
        tags.append(
            f'<Tag Name="{n}" DataType="STRING"><Data Format="String" Length="{lens[i]}"><![CDATA[{raw}]]></Data></Tag>'
        )
    e.case("S_strings", env("Tag", "x", ctag("".join(tags))))
    e.export("all", "Controller/Tags/Tag")
    e.write()
    (HERE / "exp11" / "lits.json").write_text(json.dumps(lits))


def exp12_edit(p):
    """Structural edits via the py_l5x API (tags, operand metadata, routines, rungs, ST)."""
    ct = p.controller_tags
    ct.add("gen_dint", "DINT", description="generated dint")
    ct.add("gen_timer", "TIMER", description="generated timer")
    ct.add("gen_udt", "A_UDT")
    ct.add("gen_aoi", "Debounce")
    ct.add("gen_arr", "TIMER", dimensions=3)
    ct.add("gen_arr2d", "INT", dimensions=(2, 3), radix="Hex")
    ct.add("gen_str", "STRING")
    ct.add("gen_const", "DINT", constant=True)
    ct.add_alias("gen_alias", "gen_dint")
    ct["gen_dint"].value = 77
    ct["gen_str"].value = "made by py_l5x"
    t = ct["gen_timer"]
    t.set_operand_comment(".PRE", "preset cmt")
    t.set_operand_comment(".DN", "done cmt")
    ct["gen_arr"].set_operand_comment("[1].PRE", "arr elem cmt")
    ct["gen_arr"].set_operand_comment("[0]", "arr elem0 cmt")
    ct["gen_udt"].set_operand_metadata(".A_DINT", "engineering_unit", "mm")
    ct["gen_udt"].set_operand_metadata(".A_DINT", "max", "100")
    ct["gen_udt"].set_operand_metadata(".A_DINT", "min", "-5")
    mp = p.programs["MainProgram"]
    mp.tags.remove("an_unsigned_sint")
    mp.tags.rename("a_character", "renamed_char")
    mp.tags.add("prog_new", "BOOL")
    r = mp.routines.add("GenRLL", description="generated routine")
    r.add_rung("XIC(prog_new)OTE(gen_timer.EN);", comment="first generated rung")
    r.add_rung("MOVE(gen_const,gen_dint);")
    r.add_rung("TON(gen_timer,?,?);", index=0)
    r.add_rung("NOP();")
    r.remove_rung(3)
    st = mp.routines.add("GenST", "ST")
    st.set_st_lines(
        [
            "// generated ST",
            "IF prog_new THEN",
            "    gen_dint := gen_dint + 1;",
            "",
            "END_IF;",
        ]
    )
    mp.routines.rename("GenST", "GenST2")
    main = mp.routines["MainRoutine"]
    main.add_rung("JSR(GenRLL,0);", comment="call generated routine")
    main.add_rung("JSR(GenST2,0);")
    # program with no tags gets a tag; unscheduled program gets a routine
    p.programs["Unscheduled"].tags.add("added_to_unscheduled", "REAL")
    p.programs["Unscheduled"].routines.add("EmptyRLL")
    p.programs["Unscheduled"].routines.add("EmptyST", "ST")


def exp12():
    py_l5x = _py_l5x()
    p = py_l5x.load(str(FIX / "example.L5X"))
    exp12_edit(p)
    d = HERE / "exp12"
    d.mkdir(exist_ok=True)
    p.write(d / "edited.L5X")
    e = Exp("exp12", base="C:/Users/zwood/ldsdk/projects/exp12/edited.L5X")
    e.files = {"edited.L5X": (d / "edited.L5X").read_bytes()}
    e.raw(id="build", op="build")
    for n in [
        "gen_dint",
        "gen_timer",
        "gen_udt",
        "gen_aoi",
        "gen_arr",
        "gen_arr2d",
        "gen_str",
        "gen_const",
        "gen_alias",
    ]:
        e.export(n, CT(n))
    e.export("mainprogram", PR("MainProgram"))
    e.export("unscheduled", PR("Unscheduled"))
    e.export("empty_rll", RT("Unscheduled", "EmptyRLL"))
    # component path: edited program fixture imported into the example base as a new program
    comp = py_l5x.load(str(FIX / "MainProgram_Program.L5X"))
    cp = comp.programs["MainProgram"]
    cp.name = "MainProgramCopy"
    cp.tags.add("comp_new", "DINT")
    cp.routines["MainRoutine"].add_rung(
        "MOVE(5,comp_new);", comment="component rung", index=0
    )
    # the target name in the header must follow the rename
    comp.root.set("TargetName", "MainProgramCopy")
    e.files["c_prog.L5X"] = py_l5x.writer.to_bytes(comp.root)
    e.steps.append(
        {
            "id": "C1_prog_component",
            "op": "import",
            "file": "c_prog.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    e.export("c_prog", PR("MainProgramCopy"))
    e.write()


def _product_defined_names():
    import re as _re

    t = (HERE / "results" / "exp02a" / "all_product_defined.L5X").read_text(
        encoding="utf-8-sig"
    )
    return _re.findall(r'<DataType Use="Target" Name="([^"]+)"', t)


def exp13():
    """One data-less tag per ProductDefined type: Studio's Decorated defaults are the layout table."""
    e = Exp("exp13")
    for t in _product_defined_names():
        e.case(
            f"std_{t}",
            env(
                "Tag",
                f"bt_{t}",
                ctag(f'<Tag Use="Target" Name="bt_{t}" DataType="{t}"/>'),
            ),
        )
        e.case(
            f"saf_{t}",
            env(
                "Tag",
                f"bs_{t}",
                ctag(
                    f'<Tag Use="Target" Name="bs_{t}" Class="Safety" DataType="{t}"/>'
                ),
            ),
        )
    e.export("all_tags", "Controller/Tags/Tag")
    e.write()


def exp14():
    """Data-less tags of every fixture UDT/AOI (+arrays): golden defaults for computed layouts."""
    e = Exp("exp14")
    udts = [
        "A_UDT",
        "GenericRobotInputs",
        "GenericRobotIO",
        "GenericRobotOutputs",
        "robotAlarmCode",
        "robotString",
        "robotUI",
        "robotUO",
        "simple_udt",
    ]
    aoi_names = [
        "Debounce",
        "GenericInput",
        "FanucAlarmLookup",
        "FanucPNS",
        "SeqCtrl",
        "FanucRobot",
    ]
    tags = []
    for t in udts + aoi_names:
        tags.append(f'<Tag Name="d_{t}" DataType="{t}"/>')
    for t, dims in [
        ("A_UDT", "2"),
        ("Debounce", "2"),
        ("robotString", "3"),
        ("TIMER", "2"),
        ("DINT", "2 3"),
        ("BOOL", "40"),
        ("STRING", "2"),
        ("simple_udt", "2 2"),
    ]:
        tags.append(
            f'<Tag Name="a_{t}_{dims.replace(" ", "x")}" DataType="{t}" Dimensions="{dims}"/>'
        )
    # a UDT using BOOLs in host form, plain-BOOL form, nested built-ins, a STRING member and arrays of each
    tags_udt = udt_d(
        "DefMix",
        mem("ZZZZZZZZZZDefMix0", "SINT", extra=' Hidden="true"')
        + mem("b0", "BIT", extra=' Target="ZZZZZZZZZZDefMix0" BitNumber="0"')
        + mem("b1", "BIT", extra=' Target="ZZZZZZZZZZDefMix0" BitNumber="1"')
        + mem("t", "TIMER")
        + mem("ta", "TIMER", 2)
        + mem("s", "STRING")
        + mem("rs", "robotString")
        + mem("x", "REAL", 3)
        + mem("flags", "BOOL", 32)
        + mem("su", "simple_udt")
        + mem("deb", "Debounce"),
        ["simple_udt", "robotString"],
    )
    e.case(
        "D0_udt",
        env("DataType", "DefMix", dts(tags_udt.replace("</DataType>", "</DataType>"))),
    )
    tags.append('<Tag Name="d_DefMix" DataType="DefMix"/>')
    tags.append('<Tag Name="a_DefMix_2" DataType="DefMix" Dimensions="2"/>')
    e.case("D1_tags", env("Tag", "x", ctag("".join(tags))))
    e.export("all_tags", "Controller/Tags/Tag")
    e.export("defmix", DT("DefMix"))
    e.write()


# (name, data_type, dimensions, value) - assigned via tags.add(..., value=...)
EXP15_TAGS = [
    ("v_timer", "TIMER", None, {"PRE": 5000, "ACC": 12, "EN": True}),
    ("v_counter", "COUNTER", None, {"PRE": 10}),
    ("v_control", "CONTROL", None, {"LEN": 7, "POS": 3}),
    ("v_pid", "PID", None, {"SP": 50.5, "KP": 1.25}),
    (
        "v_udt",
        "A_UDT",
        None,
        {
            "a_Bool": True,
            "a_real": 3.5,
            "a_nested_UDT": {"lint": 77, "bool3": True},
            "an_array": [0.5, 1.5, 2.5, 3.5],
            "an_aoi": {"onDelay": 111},
        },
    ),
    ("v_aoi", "SeqCtrl", None, {"startupStep": 10, "mode": True}),
    ("v_dint2d", "DINT", (2, 3), [[1, 2, 3], [4, 5, 6]]),
    ("v_timers", "TIMER", 3, {1: {"PRE": 2500}}),
    ("v_bools", "BOOL", 40, {0: True, 39: True}),
    ("v_str", "STRING", None, "generated"),
    ("v_rstr", "robotString", None, "robot text"),
    ("v_strs", "STRING", 2, ["first", "second"]),
    ("v_udts", "simple_udt", 2, [{"Dint": 1}, {"Dint": 2, "real": 9}]),
    ("v_real", "REAL", None, 1.5),
]

COMPONENT_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="37.00" TargetType="Tag" ContainsContext="true">
<Controller Use="Context" Name="Example_PLC">
<DataTypes Use="Context">
</DataTypes>
<Tags Use="Context">
</Tags>
</Controller>
</RSLogix5000Content>
"""


def exp15():
    """Structured values: full-project tags.add(value=...) and a component generated from a template."""
    py_l5x = _py_l5x()
    p = py_l5x.load(str(FIX / "example.L5X"))
    expected = {}
    for name, dt, dims, val in EXP15_TAGS:
        t = p.controller_tags.add(name, dt, dimensions=dims, value=val)
        expected[name] = t.to_python()
    d = HERE / "exp15"
    d.mkdir(exist_ok=True)
    p.write(d / "edited.L5X")
    (d / "expected.json").write_text(json.dumps(expected, default=str))
    e = Exp("exp15", base="C:/Users/zwood/ldsdk/projects/exp15/edited.L5X")
    e.files = {"edited.L5X": (d / "edited.L5X").read_bytes()}
    e.raw(id="build", op="build")
    e.export("full_tags", "Controller/Tags/Tag")
    # component: start from an empty template, context types from the example project
    comp = py_l5x.loads(COMPONENT_TEMPLATE)
    comp.controller_tags  # noqa: B018
    # the component's TypeRegistry has no UDT/AOI definitions, so only built-in/atomic types here
    for name, dt, dims, val in EXP15_TAGS:
        if dt in ("A_UDT", "SeqCtrl", "robotString", "simple_udt"):
            continue
        comp.controller_tags.add("c_" + name, dt, dimensions=dims, value=val)
    e.files["component.L5X"] = py_l5x.writer.to_bytes(comp.root)
    e.steps.append(
        {
            "id": "C1_component_tags",
            "op": "import",
            "file": "component.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    e.export("comp_tags", "Controller/Tags/Tag")
    e.raw(id="build2", op="build")
    e.write()


def exp15_check():
    """Compare Studio's exported values with what py_l5x produced."""
    py_l5x = _py_l5x()
    expected = json.loads((HERE / "exp15" / "expected.json").read_text())
    full = py_l5x.load(str(HERE / "results" / "exp15" / "full_tags.L5X"))
    comp = py_l5x.load(str(HERE / "results" / "exp15" / "comp_tags.L5X"))
    bad = 0
    for name, exp in expected.items():
        for label, proj, tname in (("full", full, name), ("comp", comp, "c_" + name)):
            if tname not in proj.controller_tags:
                if label == "comp" and name in ("v_udt", "v_aoi", "v_rstr", "v_udts"):
                    continue
                print(f"MISSING {label} {tname}")
                bad += 1
                continue
            got = json.loads(
                json.dumps(proj.controller_tags[tname].to_python(), default=str)
            )
            if got != exp:
                bad += 1
                print(f"DIFF {label} {tname}:\n  exp {exp}\n  got {got}")
    print("all values match" if not bad else f"{bad} problems")


def exp16():
    """Get real L5K text (to use L5K import as a BOOL-packing oracle)."""
    e = Exp("exp16")
    e.raw(id="save_l5k", op="save_as", name="example.L5K")
    e.write()


def exp16b():
    e = Exp("exp16b", base=BLANK_ACD)
    e.raw(id="save_l5k", op="save_as", name="blank.L5K")
    e.write()


PACK_UDTS = {
    # name: L5K member lines (BOOLs declared plainly; Studio decides packing)
    "PkTen": [f"BOOL b{i};" for i in range(10)],
    "PkSplit": [
        "BOOL a0;",
        "BOOL a1;",
        "DINT x;",
        "BOOL c0;",
        "SINT s;",
        "BOOL d0;",
        "BOOL d1;",
        "BOOL d2;",
    ],
    "PkSeventeen": ["DINT first;"]
    + [f"BOOL b{i};" for i in range(17)]
    + ["REAL last;"],
    "PkBoolArr": ["BOOL flags[32];", "BOOL single;", "BOOL flags2[64];", "BOOL tail;"],
    "PkVeryLongUdtNameX": ["BOOL a;", "DINT x;", "BOOL b;"],
    "PkNested": ["PkTen inner;", "BOOL after;", "TIMER t;", "BOOL last;"],
}


def exp16c():
    """L5K import as BOOL-packing oracle: plain BOOL members, Studio packs them."""
    base = (HERE / "results" / "exp16b" / "blank.L5K").read_text(encoding="utf-8-sig")
    dts = ""
    for n, lines in PACK_UDTS.items():
        dts += (
            f"\tDATATYPE {n} (FamilyType := NoFamily)\n"
            + "".join(f"\t\t{l}\n" for l in lines)
            + "\tEND_DATATYPE\n\n"
        )
    # insert before the first MODULE (datatypes come first in a controller block)
    i = base.index("\tMODULE ")
    txt = base[:i] + dts + base[i:]
    d = HERE / "exp16c"
    d.mkdir(exist_ok=True)
    (d / "packing.L5K").write_bytes(
        txt.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    )
    e = Exp("exp16c", base="C:/Users/zwood/ldsdk/projects/exp16c/packing.L5K")
    e.files = {}
    e.raw(id="save_l5x", op="save_as", name="packing.L5X")
    e.write()
    (d / "packing.L5K").write_bytes(
        txt.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
    )


def exp17():
    """Built UDTs: component import (packed layout, deps) and full project with <Dependencies> added."""
    py_l5x = _py_l5x()
    from py_l5x import DataTypeSpec, MemberSpec, build_datatype
    from py_l5x.parsers import schema

    specs = [
        DataTypeSpec(
            "BdInner",
            [
                MemberSpec("x", "DINT"),
                MemberSpec("on", "BOOL", description="inner bool"),
            ],
        ),
        DataTypeSpec(
            "BdMain",
            [MemberSpec(f"b{i}", "BOOL") for i in range(10)]
            + [
                MemberSpec(
                    "speed",
                    "REAL",
                    engineering_unit="rpm",
                    min=0,
                    max=1800,
                    description="Speed",
                ),
                MemberSpec("inner", "BdInner"),
                MemberSpec("deb", "Debounce"),
                MemberSpec("t", "TIMER"),
                MemberSpec("flags", "BOOL", 40),
                MemberSpec("last", "BOOL", state0="off", state1="on"),
            ],
            description="built by py_l5x",
        ),
        DataTypeSpec.string("BdStr", 20),
        DataTypeSpec(
            "BdEight",
            [MemberSpec(f"b{i}", "BOOL") for i in range(8)] + [MemberSpec("x", "DINT")],
        ),
    ]
    # component file: target UDTs first (dependents before dependencies, as Studio exports)
    comp = py_l5x.loads(
        COMPONENT_TEMPLATE.replace('TargetType="Tag"', 'TargetType="DataType"')
    )
    dts_el = comp.root.find("Controller/DataTypes")
    reg = py_l5x.load(str(FIX / "example.L5X"))._type_registry
    for sp in specs:
        schema.insert_child(dts_el, build_datatype(sp, reg))
    for sp in specs:
        comp.controller_tags.add("bt_" + sp.name, sp.name)
    e = Exp("exp17")
    e.files = {"component.L5X": py_l5x.writer.to_bytes(comp.root)}
    e.steps.append(
        {
            "id": "C1_built_udts",
            "op": "import",
            "file": "component.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    for sp in specs:
        e.export(sp.name, DT(sp.name))
    e.raw(id="raw_BdEight", op="get", xpath=CT("bt_BdEight"), type="raw")
    e.raw(id="raw_BdMain", op="get", xpath=CT("bt_BdMain"), type="raw")
    e.raw(id="build", op="build")
    e.write()
    (HERE / "exp17" / "built").mkdir(exist_ok=True)
    for sp in specs:
        (HERE / "exp17" / "built" / f"{sp.name}.xml").write_text(
            py_l5x.writer.to_string(build_datatype(sp, reg))
        )


def exp17b():
    """Full project where every UDT is rebuilt from its spec WITH <Dependencies> (exports have none)."""
    py_l5x = _py_l5x()
    from py_l5x import build_datatype

    p = py_l5x.load(str(FIX / "example.L5X"))
    dts_el = p.root.find("Controller/DataTypes")
    for i, el in enumerate(list(dts_el)):
        spec = p.data_types[el.get("Name")].to_spec()
        new = build_datatype(spec, p._type_registry)
        new.tail = el.tail
        dts_el.remove(el)
        dts_el.insert(i, new)
    d = HERE / "exp17b"
    d.mkdir(exist_ok=True)
    p.write(d / "rebuilt.L5X")
    e = Exp("exp17b", base="C:/Users/zwood/ldsdk/projects/exp17b/rebuilt.L5X")
    e.files = {"rebuilt.L5X": (d / "rebuilt.L5X").read_bytes()}
    e.raw(id="build", op="build")
    e.export("a_udt", DT("A_UDT"))
    e.export("gio", DT("GenericRobotIO"))
    e.raw(id="save", op="save_as", name="resaved.L5X")
    e.write()


def exp18():
    """How Studio converts member values when a UDT member type changes on overwrite."""
    e = Exp("exp18", base=BLANK_ACD)
    vals = [
        ("r1", "REAL", "2.7"),
        ("r2", "REAL", "-2.7"),
        ("r3", "REAL", "2.5"),
        ("r4", "REAL", "3.5"),
        ("r5", "REAL", "1e10"),
        ("d1", "DINT", "300"),
        ("d2", "DINT", "-1"),
        ("d3", "DINT", "2147483647"),
        ("b1", "BOOL", "1"),
        ("s1", "SINT", "-5"),
    ]
    e.case(
        "X1_udt",
        env(
            "DataType", "Conv", dts(udt("Conv", "".join(mem(n, t) for n, t, _ in vals)))
        ),
    )
    struct = "".join(
        f'<DataValueMember Name="{n}" DataType="{t}" Value="{v}"/>' for n, t, v in vals
    )
    e.case(
        "X2_tag",
        env(
            "Tag",
            "conv",
            ctag(
                f'<Tag Use="Target" Name="conv" DataType="Conv">{dec("<Structure DataType=" + chr(34) + "Conv" + chr(34) + ">" + struct + "</Structure>")}</Tag>'
            ),
        ),
    )
    # change: REAL->DINT, DINT->SINT (overflow), DINT->BOOL, BOOL->REAL, SINT->UINT (negative to unsigned)
    new = {
        "r1": "DINT",
        "r2": "DINT",
        "r3": "DINT",
        "r4": "DINT",
        "r5": "DINT",
        "d1": "SINT",
        "d2": "BOOL",
        "d3": "REAL",
        "b1": "REAL",
        "s1": "UINT",
    }
    e.case(
        "X3_change",
        env(
            "DataType",
            "Conv",
            dts(udt("Conv", "".join(mem(n, new[n]) for n, _, _ in vals))),
        ),
        export=[CT("conv")],
    )
    e.write()


def exp18b():
    """Numeric -> BOOL conversion: nonzero or low bit?"""
    e = Exp("exp18b", base=BLANK_ACD)
    vals = [
        ("d2", "DINT", "2"),
        ("d4", "DINT", "4"),
        ("d3", "DINT", "3"),
        ("d0", "DINT", "0"),
        ("r05", "REAL", "0.5"),
        ("r2", "REAL", "2.0"),
    ]
    e.case(
        "Y1_udt",
        env(
            "DataType",
            "ConvB",
            dts(udt("ConvB", "".join(mem(n, t) for n, t, _ in vals))),
        ),
    )
    struct = "".join(
        f'<DataValueMember Name="{n}" DataType="{t}" Value="{v}"/>' for n, t, v in vals
    )
    e.case(
        "Y2_tag",
        env(
            "Tag",
            "convb",
            ctag(
                f'<Tag Use="Target" Name="convb" DataType="ConvB">{dec("<Structure DataType=" + chr(34) + "ConvB" + chr(34) + ">" + struct + "</Structure>")}</Tag>'
            ),
        ),
    )
    e.case(
        "Y3_change",
        env(
            "DataType",
            "ConvB",
            dts(udt("ConvB", "".join(mem(n, "BOOL") for n, _, _ in vals))),
        ),
        export=[CT("convb")],
    )
    e.write()


def exp19_specs(p):
    """The UDT changes under test, applied to a loaded example project's specs."""
    from py_l5x import MemberSpec

    su = p.data_types["simple_udt"].to_spec()
    m = {x.name: x for x in su.members}
    # reorder, insert a member in the middle, change Dint DINT->REAL, real DINT->SINT, drop bool4
    su.members = [
        m["lint"],
        m["bool1"],
        MemberSpec("inserted", "INT"),
        m["bool2"],
        m["bool3"],
        MemberSpec("Dint", "REAL"),
        MemberSpec("real", "SINT"),
    ]
    return su


def exp19():
    """UDT replace: our migration (full project) vs Studio's own migration (component import)."""
    py_l5x = _py_l5x()
    from py_l5x import build_datatype
    from py_l5x.parsers import schema

    seed = {
        "a_simple_udt_instance": {
            "bool1": True,
            "bool4": True,
            "Dint": 70000,
            "real": 300,
            "lint": 9,
        },
        "a_simple_udt_with_overrides": {
            "bool2": True,
            "Dint": -1,
            "real": -129,
            "lint": -5,
        },
    }
    # 1) seeded project (both paths start from this)
    p = py_l5x.load(str(FIX / "example.L5X"))
    for t, v in seed.items():
        p.programs["MainProgram"].tags[t].value = v
    p.programs["MainProgram"].tags["a_udt_instance"].value = {
        "a_nested_UDT": {"Dint": 123, "real": 7, "bool3": True}
    }
    d = HERE / "exp19"
    d.mkdir(exist_ok=True)
    p.write(d / "seeded.L5X")
    # 2) our migration
    ours = py_l5x.load(str(d / "seeded.L5X"))
    ours.data_types.replace(exp19_specs(ours))
    ours.write(d / "ours.L5X")
    # 3) Studio's migration: component file with just the new simple_udt, imported over the seeded project
    comp = py_l5x.loads(
        COMPONENT_TEMPLATE.replace('TargetType="Tag"', 'TargetType="DataType"')
    )
    ref = py_l5x.load(str(d / "seeded.L5X"))
    schema.insert_child(
        comp.root.find("Controller/DataTypes"),
        build_datatype(exp19_specs(ref), ref._type_registry),
    )
    e = Exp("exp19", base="C:/Users/zwood/ldsdk/projects/exp19/seeded.L5X")
    e.files = {
        "seeded.L5X": (d / "seeded.L5X").read_bytes(),
        "ours.L5X": (d / "ours.L5X").read_bytes(),
        "studio_udt.L5X": py_l5x.writer.to_bytes(comp.root),
    }
    e.steps.append(
        {
            "id": "S1_studio_migrates",
            "op": "import",
            "file": "studio_udt.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    e.raw(id="build_studio", op="build")
    e.export("studio_mainprogram", PR("MainProgram"))
    e.write()


def exp19b():
    e = Exp("exp19b", base="C:/Users/zwood/ldsdk/projects/exp19/ours.L5X")
    e.raw(id="build_ours", op="build")
    e.export("ours_mainprogram", PR("MainProgram"))
    e.write()


def exp19_check():
    py_l5x = _py_l5x()
    s = (
        py_l5x.load(str(HERE / "results" / "exp19" / "studio_mainprogram.L5X"))
        .programs["MainProgram"]
        .tags
    )
    o = (
        py_l5x.load(str(HERE / "results" / "exp19b" / "ours_mainprogram.L5X"))
        .programs["MainProgram"]
        .tags
    )
    local = py_l5x.load(str(HERE / "exp19" / "ours.L5X")).programs["MainProgram"].tags
    bad = 0
    for t in ["a_simple_udt_instance", "a_simple_udt_with_overrides", "a_udt_instance"]:
        sv, ov, lv = s[t].to_python(), o[t].to_python(), local[t].to_python()
        if t == "a_udt_instance":
            sv, ov, lv = sv["a_nested_UDT"], ov["a_nested_UDT"], lv["a_nested_UDT"]
        ok = sv == ov == lv
        bad += not ok
        print(
            ("SAME " if ok else "DIFF ") + t,
            "\n  studio:",
            sv,
            "\n  ours  :",
            ov,
            "\n  local :",
            lv,
        )
    print("all identical" if not bad else f"{bad} differ")


def exp20():
    """Built AOIs imported as components; Studio's export compared to the builder output."""
    py_l5x = _py_l5x()
    from py_l5x import (
        AOISpec,
        DataTypeSpec,
        LocalTagSpec,
        MemberSpec,
        ParameterSpec,
        RoutineSpec,
        RungSpec,
        build_aoi,
        build_datatype,
    )
    from py_l5x.parsers import schema

    ref = py_l5x.load(str(FIX / "example.L5X"))
    reg = ref._type_registry
    aois_ = [
        AOISpec(
            "BaMin",
            [
                ParameterSpec("In1", "BOOL"),
                ParameterSpec("Out1", "BOOL", usage="Output"),
            ],
            routines=[RoutineSpec("Logic", rungs=[RungSpec("XIC(In1)OTE(Out1);")])],
        ),
        AOISpec(
            "BaFull",
            [
                ParameterSpec(
                    "Run", "BOOL", required=True, visible=True, description="run cmd"
                ),
                ParameterSpec(
                    "Speed",
                    "REAL",
                    default=12.5,
                    engineering_unit="rpm",
                    min=0,
                    max=100,
                    visible=True,
                ),
                ParameterSpec("Data", "simple_udt", usage="InOut", required=True),
                ParameterSpec(
                    "Done",
                    "BOOL",
                    usage="Output",
                    visible=True,
                    state0="no",
                    state1="yes",
                ),
            ],
            local_tags=[
                LocalTagSpec("t", "TIMER", default={"PRE": 1500}),
                LocalTagSpec("arr", "DINT", dimension=4, default=[1, 2, 3, 4]),
                LocalTagSpec("deb", "Debounce"),
                LocalTagSpec("s", "STRING", default="hi"),
            ],
            routines=[
                RoutineSpec(
                    "Logic",
                    rungs=[
                        RungSpec("XIC(Run)TON(t,?,?);", comment="delay"),
                        RungSpec("XIC(t.DN)OTE(Done);"),
                        RungSpec("MOVE(Speed,Data.real);"),
                        RungSpec("Debounce(deb);"),
                    ],
                ),
                RoutineSpec("Prescan", type_="ST", lines=["Done := 0;"]),
                RoutineSpec("EnableInFalse", rungs=[RungSpec("OTU(Done);")]),
            ],
            revision="2.3",
            revision_note="built by py_l5x",
            description="full featured",
            vendor="AIC",
        ),
    ]
    comp = py_l5x.loads(
        COMPONENT_TEMPLATE.replace(
            'TargetType="Tag"', 'TargetType="AddOnInstructionDefinition"'
        )
    )
    c = comp.root.find("Controller")
    aoi_el = ET.Element("AddOnInstructionDefinitions")
    schema.insert_child(c, aoi_el)
    for a in aois_:
        schema.insert_child(aoi_el, build_aoi(a, reg))
    e = Exp("exp20")
    e.files = {"aois.L5X": py_l5x.writer.to_bytes(comp.root)}
    e.steps.append(
        {
            "id": "A1_built_aois",
            "op": "import",
            "file": "aois.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    for a in aois_:
        e.export(a.name, AOI(a.name))
    # calls + tags so the build exercises them
    e.files["prog.L5X"] = env(
        "Program",
        "BaProg",
        progs(
            prog(
                "BaProg",
                '<Tag Name="m" DataType="BaMin"/><Tag Name="f" DataType="BaFull"/><Tag Name="u" DataType="simple_udt"/><Tag Name="go" DataType="BOOL"/>',
                rll("MainRoutine", "BaMin(m);", "BaFull(f,go,u);"),
            )
        ),
    ).encode()
    e.steps.append(
        {
            "id": "A2_prog",
            "op": "import",
            "file": "prog.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    e.raw(id="build", op="build")
    # questionable: Input array parameter (hand-made, builder refuses it)
    e.case(
        "Q1_input_array_param",
        env(
            "AddOnInstructionDefinition",
            "BaQ1",
            aois(
                aoi(
                    "BaQ1",
                    par("Arr", "DINT", extra=' Dimensions="4"')
                    + par("O", "BOOL", "Output"),
                    routines=rll("Logic", "OTE(O);"),
                )
            ),
        ),
        export=[AOI("BaQ1")],
    )
    e.case(
        "Q2_input_udt_param",
        env(
            "AddOnInstructionDefinition",
            "BaQ2",
            aois(
                aoi(
                    "BaQ2",
                    par("U", "simple_udt") + par("O", "BOOL", "Output"),
                    routines=rll("Logic", "OTE(O);"),
                )
            ),
        ),
        export=[AOI("BaQ2")],
    )
    e.write()
    (HERE / "exp20" / "built").mkdir(exist_ok=True)
    for a in aois_:
        (HERE / "exp20" / "built" / f"{a.name}.xml").write_text(
            py_l5x.writer.to_string(build_aoi(a, reg))
        )


def exp20_check():
    """Compare Studio's exports of the built AOIs with the builder output."""
    import difflib
    import re as _re

    def norm(t):
        t = t.replace("\r\n", "\n")
        # Studio adds dates/users/SoftwareRevision/Class and L5K DefaultData; py_l5x writes neither
        t = _re.sub(
            r'\s*(CreatedDate|CreatedBy|EditedDate|EditedBy|SoftwareRevision|Class)="[^"]*"',
            "",
            t,
        )
        t = _re.sub(
            r'<DefaultData Format="L5K">\n<!\[CDATA\[.*?\]\]>\n</DefaultData>\n',
            "",
            t,
            flags=_re.S,
        )
        return _re.sub(r"\s+>", ">", t)

    for n in ["BaMin", "BaFull"]:
        built = (
            (HERE / "exp20" / "built" / f"{n}.xml")
            .read_text()
            .split("\n", 1)[1]
            .strip()
        )
        exp = (
            (HERE / "results" / "exp20" / f"{n}.L5X")
            .read_text(encoding="utf-8-sig")
            .replace("\r\n", "\n")
        )
        m = _re.search(
            r'<AddOnInstructionDefinition Use="Target" (.*?)\n</AddOnInstructionDefinition>',
            exp,
            _re.S,
        )
        got, b = (
            norm(
                "<AddOnInstructionDefinition "
                + m[1]
                + "\n</AddOnInstructionDefinition>"
            ),
            norm(built),
        )
        print(n, "IDENTICAL" if got == b else "DIFF")
        if got != b:
            print(
                "\n".join(
                    list(
                        difflib.unified_diff(
                            b.splitlines(), got.splitlines(), lineterm=""
                        )
                    )[:40]
                )
            )


def exp20b():
    """Which Required/Visible combinations Studio accepts per usage."""
    e = Exp("exp20b")
    combos = [
        ("InOut", "true", "false"),
        ("InOut", "false", "true"),
        ("InOut", "false", "false"),
        ("InOut", "true", "true"),
        ("Input", "true", "false"),
        ("Input", "false", "true"),
        ("Output", "true", "false"),
        ("Output", "false", "true"),
    ]
    for i, (usage, req, vis) in enumerate(combos):
        n = f"RV{i}"
        dt = "simple_udt" if usage == "InOut" else "DINT"
        extra = f' Required="{req}" Visible="{vis}"'
        e.case(
            f"RV{i}_{usage}_req{req}_vis{vis}",
            env(
                "AddOnInstructionDefinition",
                n,
                aois(
                    aoi(
                        n,
                        par("P", dt, usage, extra=extra) + par("O", "BOOL", "Output"),
                        routines=rll("Logic", "OTE(O);"),
                    )
                ),
            ),
            export=[AOI(n)],
        )
    e.write()


def exp21_spec(p):
    from py_l5x import ParameterSpec

    sp = p.aois["Debounce"].to_spec()
    params = {x.name: x for x in sp.parameters}
    params["onDelay"].data_type = "REAL"
    params["onDelay"].radix = None
    params["onDelay"].min = None
    params["onDelay"].max = None
    sp.parameters = [
        params["state"],
        ParameterSpec("hold", "DINT", default=42),
        params["onDelay"],
        params["offDelay"],
    ]
    sp.revision = "1.5"
    return sp


def exp21():
    """AOI replace: our migration vs Studio's import migration; AOI rename builds."""
    py_l5x = _py_l5x()
    from py_l5x import build_aoi
    from py_l5x.parsers import schema

    p = py_l5x.load(str(FIX / "example.L5X"))
    p.controller_tags.add(
        "deb_tag", "Debounce", value={"state": True, "onDelay": 1234, "offDelay": 77}
    )
    gi = p.aois["GenericInput"]
    gi.local_tags["debounce"].value = {"onDelay": 555, "offDelay": 66}
    d = HERE / "exp21"
    d.mkdir(exist_ok=True)
    p.write(d / "seeded.L5X")
    ours = py_l5x.load(str(d / "seeded.L5X"))
    ours.aois.replace(exp21_spec(ours))
    ours.write(d / "ours.L5X")
    ren = py_l5x.load(str(FIX / "example.L5X"))
    ren.aois.rename("SeqCtrl", "SeqControl")
    ren.write(d / "renamed.L5X")
    ref = py_l5x.load(str(d / "seeded.L5X"))
    comp = py_l5x.loads(
        COMPONENT_TEMPLATE.replace(
            'TargetType="Tag"', 'TargetType="AddOnInstructionDefinition"'
        )
    )
    el = ET.Element("AddOnInstructionDefinitions")
    schema.insert_child(comp.root.find("Controller"), el)
    schema.insert_child(el, build_aoi(exp21_spec(ref), ref._type_registry))
    e = Exp("exp21", base="C:/Users/zwood/ldsdk/projects/exp21/seeded.L5X")
    e.files = {
        "seeded.L5X": (d / "seeded.L5X").read_bytes(),
        "ours.L5X": (d / "ours.L5X").read_bytes(),
        "renamed.L5X": (d / "renamed.L5X").read_bytes(),
        "studio_aoi.L5X": py_l5x.writer.to_bytes(comp.root),
    }
    e.steps.append(
        {
            "id": "S1_studio_migrates",
            "op": "import",
            "file": "studio_aoi.L5X",
            "xpath": "Controller",
            "coll": "overwrite",
        }
    )
    e.raw(id="build_studio", op="build")
    e.export("studio_deb_tag", CT("deb_tag"))
    e.export("studio_gi", AOI("GenericInput"))
    e.write()
    for run, f in (("exp21b", "ours.L5X"), ("exp21c", "renamed.L5X")):
        x = Exp(run, base=f"C:/Users/zwood/ldsdk/projects/exp21/{f}")
        x.raw(id="build", op="build")
        if run == "exp21b":
            x.export("ours_deb_tag", CT("deb_tag"))
            x.export("ours_gi", AOI("GenericInput"))
        else:
            x.export("seq", AOI("SeqControl"))
        x.write()


def exp21_check():
    py_l5x = _py_l5x()
    st = (
        py_l5x.load(str(HERE / "results" / "exp21" / "studio_deb_tag.L5X"))
        .controller_tags["deb_tag"]
        .to_python()
    )
    ou = (
        py_l5x.load(str(HERE / "results" / "exp21b" / "ours_deb_tag.L5X"))
        .controller_tags["deb_tag"]
        .to_python()
    )
    sg = (
        py_l5x.load(str(HERE / "results" / "exp21" / "studio_gi.L5X"))
        .aois["GenericInput"]
        .local_tags["debounce"]
        .to_python()
    )
    og = (
        py_l5x.load(str(HERE / "results" / "exp21b" / "ours_gi.L5X"))
        .aois["GenericInput"]
        .local_tags["debounce"]
        .to_python()
    )
    for label, a, b in (("deb_tag", st, ou), ("GenericInput.debounce", sg, og)):
        print(
            ("SAME " if a == b else "DIFF ") + label, "\n  studio:", a, "\n  ours  :", b
        )


if __name__ == "__main__":
    for name in sys.argv[1:]:
        globals()[name]()
