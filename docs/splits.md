# Object boundaries and link order

[`config/GALE01/splits.txt`](../config/GALE01/splits.txt) assigns ranges of
the original US v1.02 executable to compilation units. A unit is the object
produced from one source file. Decomp-toolkit uses these ranges to generate
reference objects and resolve their link order.

## How the build files fit together

| File | Role |
| --- | --- |
| [`config.yml`](../config/GALE01/config.yml) | Select the original DOL, its hash, and the symbol and split files. |
| [`symbols.txt`](symbols.md) | Name functions, data objects, and labels within sections. |
| [`splits.txt`](../config/GALE01/splits.txt) | Assign section ranges to compilation units. |
| [`configure.py`](../configure.py) | Select source files, compiler settings, and whether the linker uses each compiled object. |
| [`src`](../src) | Supply the C and assembly implementations. |

For example, `Object(Matching, "melee/lb/lbcommand.c")` in `configure.py`
selects the rebuilt command object for linking. Its split entry describes
the reference object's original ranges. A file marked incomplete can use
an extracted original object instead. The [verification tool](../tools/verify.py)
checks source completion as well as the final executable, so this fallback
cannot hide incomplete source during cleanup.

## Section header and source entries

This is an excerpt from the actual configuration. The complete file also
declares other sections.

```text
Sections:
    .text       type:code align:32
    .data       type:data align:32
    .sdata2     type:rodata align:32

melee/lb/lbcommand.c:
    .text       start:0x80005940 end:0x80005BB0
    .data       start:0x803B9840 end:0x803B9880
    .sdata2     start:0x804D79E0 end:0x804D79F0
```

The header describes the executable's sections in the toolkit's text format.
`type:` accepts `code`, `data`, `rodata`, or `bss`.
`align:` sets the section alignment in bytes.

Each source entry can cover several sections. Its name matches the object
name used in `configure.py`. For this example, the source is
[`src/melee/lb/lbcommand.c`](../src/melee/lb/lbcommand.c).

The `start:` address is included and `end:` is excluded. Addresses in this
DOL configuration are absolute. The `.text` range above therefore contains
`0x270` bytes. The next unit, `melee/lb/lbcollision.c`, starts at
`0x80005BB0`. These byte ranges remain tied to the original executable as
the source changes.

## Optional attributes

File attributes follow the source name on the same line:

| Attribute | Meaning |
| --- | --- |
| `comment:` | Override `mw_comment_version` from `config.yml` for the generated reference object. `comment:0` disables its CodeWarrior `.comment` section. |
| `order:` | Constrain a unit's order relative to other explicitly ordered units. The toolkit otherwise resolves link order from the split ranges. |

Melee has this assembly entry:

```text
MetroTRK/__exception.s: comment:0
    .init       start:0x80003298 end:0x800051CC
```

It disables compiler metadata for the reference object corresponding to
[`__exception.s`](../src/MetroTRK/__exception.s). The global
`mw_comment_version` is 8. The toolkit's
[CodeWarrior comment section notes](https://github.com/encounter/dtk-template/blob/main/docs/comment_section.md)
explain how this metadata affects the linker.

Individual section ranges also accept these attributes:

| Attribute | Meaning |
| --- | --- |
| `align:` | Override the alignment of this split's generated section. |
| `rename:` | Give the section a different name in the generated object. |
| `common` | Mark common BSS. See the toolkit's [common BSS notes](https://github.com/encounter/dtk-template/blob/main/docs/common_bss.md). |
| `skip` | Omit the range when writing the reference object. Used for linker-generated data. |

The format supports REL modules and a section `vaddr:` attribute for those
modules. They are outside this GALE01 DOL setup. See the
[toolkit format reference](https://github.com/encounter/dtk-template/blob/main/docs/splits.md)
and [v1.8.3 parser](https://github.com/encounter/decomp-toolkit/blob/v1.8.3/src/util/config.rs)
for those cases.

## Preserve boundaries during cleanup

Renaming locals, improving comments, and sharing private inline code normally
leave both `symbols.txt` and `splits.txt` unchanged. Keep the original unit
boundaries and the compiled objects selected in `configure.py`. Moving a
function to another source file can change compiler and linker behavior even
when its C statements stay the same.

Use `--no-always-apply` to prevent automatic symbol-file writes while
building. If a build stops matching, inspect the changed object and retain
its reference boundaries. Follow the [build guide](build-and-run.md)
and run `python tools/verify.py` after an intended configuration change.
