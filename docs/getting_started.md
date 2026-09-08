@page getting_started Getting started

# Melee for Mac

This is Theo's fully automated slop experiment. It is not meant for serious use
or investigation. No support, maintenance, or human review is promised. Please
do not spend time investigating or maintaining it, or send its issues upstream.

To try the app with your own game data, use the [Melee for Mac guide](native-macos.md).
The repository is [t3dotgg/melee4mac](https://github.com/t3dotgg/melee4mac).
The sections below are technical references for work Theo explicitly requests,
not a request for community investigation or contributions.

When Theo requests code changes, read the [contribution rules](../.github/CONTRIBUTING.md).
Start with the [matching build guide](build-and-run.md) and verify the original
executable before editing it. Use the [code map](code-map.md) for source locations.

# What matching means

A decompilation reconstructs C that produces the same machine instructions and
data as the original executable. Many different C programs can produce those
bytes. A matching function therefore does not prove that its source text, local
names, or comments are the original ones.

For example, [Mewtwo's special move code](../src/melee/ft/kinds/ftMewtwo/ftmewtwospecialhi.c)
has this function:

```c
void ftMt_SpecialHi_CreateGFX(HSD_GObj* gobj)
{
    Fighter* fp = GET_FIGHTER(gobj);

    ftMt_SpecialHi_SetStartGFX(gobj);
    fp->accessory4_cb = NULL;
}
```

The compiler turns the typed access into loads and stores at fixed offsets.
`GET_FIGHTER` reads the game object's user data as a `Fighter*`.
The last assignment clears that fighter's accessory callback. Types let a reader
see this meaning without working out the offsets on each read.

The compiler also chooses registers, stack slots, and instruction order.
Changing a cast, a local variable's position, or an inline helper can change
those choices. This project uses an old compiler to reproduce its original
choices. Some unusual code exists only because a simpler form did not match.

# When Theo requests cleanup

Read a function and its callers before changing it. Find the types in the
module's `types.h`, `forward.h`, and headers. Use the symbol list when a name
contains an original address:

```sh
rg -n 'plStale_UpdateStaleMovesFromFighter' src config/GALE01/symbols.txt
python tools/find_include.py StaleMoveTable
```

The header search prints textual matches. Check which header defines or
declares the symbol before adding an include.

Good cleanup has evidence:

- Rename a local value when the caller or calculation proves its purpose.
- Replace a fake type or raw offset with an existing type when its layout agrees.
- Share repeated logic with a private helper when the compiler emits the same code.
- Explain a matching workaround, ownership rule, or unusual boundary condition.

The [stale-move queue](code/stale-moves.md) and
[ARAM transfer queue](code/aram-queue.md) are worked examples. Both explain
behavior that a matching binary alone does not make clear.

Keep exported symbols, structure layouts, assertion strings, and behavior stable.
Do not give an uncertain field a confident name. A descriptive comment can state
what the code does while leaving its larger purpose unresolved.

# Check a change

Run these from a configured checkout:

```sh
python tools/check/main.py --quiet src/path/to/edited.c
python tools/verify.py
git diff --check
```

Replace the example source path with the file you edited. Run the pinned
clang-format on edited C and header files. The
[contribution rules](../.github/CONTRIBUTING.md#auto-formatting) describe the setup.

If a change stops matching, use [objdiff](https://github.com/encounter/objdiff)
with the generated `objdiff.json`. Compare the changed object. Do not hide a
regression by changing the expected hash or marking the source incomplete.

Public CI runs source style checks, tool tests, and a native static library
build. It has no original game data. Record the local full-build verification
when submitting code to this fork.

# Assembly references

You can still use [decomp.me](https://decomp.me) to study or experiment with one
function. Choose the GameCube / Wii platform and the Super Smash Bros. Melee
preset. Use the target function's assembly and the types it needs.

The build includes context targets that use the configured include paths:

```sh
ninja build/GALE01/src/melee/lb/lbcommand.ctx
```

The [context guide](code/context-generation.md) explains the generated file,
missing-header errors, and the limits of textual include expansion. The
[m2ctx tool](../tools/m2ctx/README.md) is another option for context generation.
The [PowerPC instruction reference](https://math-atlas.sourceforge.net/devel/assembly/ppc_isa.pdf)
helps explain the instructions. The GameCube uses a 32-bit PowerPC processor.

These references support requested work. They are not a call to investigate
or maintain this experiment.
