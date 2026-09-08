# Generate a source context

[`tools/decompctx.py`](../../tools/decompctx.py) expands a C file's headers into
one file for decompilation tools. After configuration, Ninja has a `.ctx` target
for each C source. Run this from the repository root:

```sh
ninja build/GALE01/src/melee/ft/fighter.ctx
```

Ninja supplies the include paths from that source's compiler flags and records
header dependencies. A header change causes the context to rebuild. These
targets do not compile or check the game executable.

Compiler `-ir` paths also search subdirectories. Configuration expands each
such path into normal include paths, starting with the directory itself and
then its subdirectories in path order. Run configuration again after adding
an include directory under one of these paths.

For a manual run with the fighter source's include paths:

```sh
python tools/decompctx.py src/melee/ft/fighter.c \
    -I src -I src/MSL -I extern/dolphin/include -I build/GALE01/include \
    -o build/GALE01/src/melee/ft/fighter.ctx \
    -d build/GALE01/src/melee/ft/fighter.ctx.d
```

The source path and each `-I` path are relative to the current directory.
Relative `-o` and `-d` paths are relative to the repository root. Absolute paths
also work. Output directories must already exist. The default output is
`ctx.c` at the repository root. Dependency names are relative to that root,
as expected when Ninja runs there.

Missing files stop generation with a nonzero exit status. A missing header
message names the source file, line, and include. Check the include paths first.
If a header must be omitted, use an explicit exclusion such as
`-x 'generated/*.h'`. The context marks excluded includes with a comment.
A source read or include error preserves the previous context and dependency
file. Each output file is replaced only after its new text has been written.

This tool expands text. It is not a C preprocessor. It does not evaluate `#if`
branches or macro includes. It expands quoted and angle-bracket includes,
including those in inactive branches. It searches the including file's folder
first, then the `-I` paths in order. A first-line `#ifndef` or `#pragma once`
prevents duplicate expansion. Assembly includes ending in `.s` remain as
include lines. The `-D NAME=VALUE` option adds a definition to the output prelude.
It does not select conditional branches during expansion.
