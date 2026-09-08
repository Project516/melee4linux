# Symbol names and addresses

[`config/GALE01/symbols.txt`](../config/GALE01/symbols.txt) describes functions,
data objects, and labels in the original US v1.02 executable. Decomp-toolkit
uses it when splitting the executable into reference objects and comparing
the rebuilt code. The path is selected by
[`config.yml`](../config/GALE01/config.yml).

These entries come from the Melee configuration:

```text
Command_Execute = .text:0x80005B64; // type:function size:0x4C scope:global
lbCommand_803B9840 = .data:0x803B9840; // type:object size:0x40 scope:global data:4byte
lbAnim_InitFrames = .text:0x8001E560; // type:function size:0xAC scope:local
```

`Command_Execute` is a 76-byte function in `.text`. Its
[source](../src/melee/lb/lbcommand.c) is in the object described by
`melee/lb/lbcommand.c` in [the split file](splits.md). `lbCommand_803B9840`
is that file's 64-byte command dispatch table. `lbAnim_InitFrames` is a local
function in [`lbanim.c`](../src/melee/lb/lbanim.c).

## Line format

```text
symbol_name = section:address; // attributes
```

For GALE01, addresses are absolute addresses in the original DOL. Numbers
can be decimal or hexadecimal with a `0x` prefix. Attributes are optional
and separated by spaces. C++ entries use the compiler's mangled symbol name.

| Attribute | Meaning |
| --- | --- |
| `type:` | `function`, `object`, or `label` |
| `size:` | Symbol size in bytes |
| `scope:` | `global`, `local`, or `weak`. An unspecified scope is treated as global. |
| `align:` | Symbol alignment in bytes |
| `data:` | How the disassembler writes the object's data |
| `hidden` | Mark the symbol hidden in the generated object. Melee uses this for exception tables. |

The supported `data:` values include `byte`, `2byte`, `4byte`, `8byte`,
`float`, `double`, `int`, `short`, `string`, `wstring`, `sjis`,
`string_table`, `wstring_table`, and `sjis_table`. This attribute controls
disassembly output. It does not declare a C type.

The format also supports these controls:

| Attribute | Meaning |
| --- | --- |
| `force_active` | Keep the symbol active in the generated object and linker script so the linker does not remove it as unused. |
| `noreloc` | Prevent the object's contents from being interpreted as relocation sources. Requires a section and a nonzero size. |
| `noexport` | Exclude the symbol from automatic export when `export_all` is enabled. |
| `stripped` | Record a symbol removed by the original linker, for cases such as common BSS matching. |

The toolkit's [CodeWarrior comment section notes](https://github.com/encounter/dtk-template/blob/main/docs/comment_section.md)
explain linker export flags. Its [common BSS notes](https://github.com/encounter/dtk-template/blob/main/docs/common_bss.md)
explain why a stripped symbol can still affect matching. The
[v1.8.3 format parser](https://github.com/encounter/decomp-toolkit/blob/v1.8.3/src/util/config.rs)
is the reference for the toolkit version selected by this checkout.

Standalone comments beginning with `//` or `#` are accepted. The toolkit
does not preserve them when it rewrites the symbol file. Put lasting
research notes in source comments or `docs/code/`.

## Keep cleanup separate from symbol changes

A local variable rename or a private inline helper normally needs no symbol
entry. Keep existing function names, sizes, and visibility during matching
cleanup. A static C function can still have a required local symbol, as
`lbAnim_InitFrames` does. Making it inline can remove code that the original
executable contains.

Configure matching work with `--no-always-apply`, as shown in the
[build guide](build-and-run.md). This disables the build's automatic
`dtk dol apply` step, which writes linked symbol information back to the
configuration. Inspect any deliberate symbol-file change and run
`python tools/verify.py`. Do not change the reference to make changed code
appear to match.
