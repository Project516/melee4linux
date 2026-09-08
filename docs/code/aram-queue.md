# ARAM transfer queue

[`lbarq.c`](../../src/melee/lb/lbarq.c) copies data from GameCube audio RAM
into main RAM. Fighter animation loading uses it before parsing an archive in
[`ftdata.c`](../../src/melee/ft/ftdata.c).

| Function | Work |
| --- | --- |
| `lbArq_80014D2C` | Initialize the node pool and lists during game startup. |
| `lbArq_80014BD0` | Invalidate the destination cache range and post a low-priority ARAM read. |
| `lbArq_80014AC4` | Handle DMA completion and call the optional user callback. |
| `lbArq_80014ABC` | Read the node state during a blocking wait. |

## Calling the transfer function

`source` is an ARAM address. `dest` is a main RAM pointer. `length` is the
number of bytes to copy. The SDK requires 32-byte alignment for the addresses
and length. The fighter loading calls round the length with `OSRoundUp32B`.

With `callback == NULL`, the function waits until the transfer finishes and
then returns the node to the free list. Call this form with interrupts enabled.
The wait restores the previous interrupt state, so a caller that already
disabled interrupts cannot receive the DMA completion interrupt.

With a callback, the function posts the transfer without waiting. The DMA
interrupt handler calls `callback(callback_arg)` after completion. The callback
must return before its node becomes free. It runs in interrupt context and must
not start a blocking transfer. Keep the destination and callback argument valid
until completion.

The SDK receives `&node->arq` as its request and the node address as the
request's `owner`. It later passes that same `ARQRequest*` to
`lbArq_80014AC4`, which recovers the node from `request->owner`.
See [`ARQPostRequest` and `__ARQInterruptServiceRoutine`](../../extern/dolphin/src/dolphin/ar/arq.c).

## Node ownership

`global->list[state]` is the head of the list for that state. Each active node
belongs to one list.

| State | Meaning | Next owner |
| --- | --- | --- |
| `FREE` | Available for allocation. | The transfer function removes the first free node and appends it to `PENDING`. |
| `PENDING` | Queued or transferring through the SDK. | The DMA completion handler appends it to `DONE`. |
| `DONE` | DMA finished, but the node is still in use. | The callback handler or blocking caller appends it to `FREE`. |

After initialization, list changes save and disable interrupts, then restore
the saved state.
The list traversal uses a pointer to a link. That link can be the list head or
the `next` field of another node. Assigning `*node_link = node->next` therefore
removes either a head node or a later node without a separate head case.

The pool has storage for ten nodes, but initialization puts only nodes 0
through 8 on the free list. The loop first links node 8 to node 9, then clears
node 8's `next` field after the loop. Preserve this nine-node limit when doing
matching cleanup. If no node is free, the transfer function asserts. It does
not wait for space.

## Matching constraints

- Keep the state getter out of line. Its call makes MWCC reload the state
  changed by the DMA interrupt. The polling loop does not yield to a scheduler.
- The first list lookup in the completion handler is equivalent to
  `&global->list[node->state]`. Direct indexing changes the generated addition
  order. The ordered `sizeof` and `offsetof` calculation preserves the match.
- The temporary assignments in the transfer function affect register
  allocation. Removing them changes the instructions, even though the C
  expressions appear equivalent.
- Keep `rp` in the allocation assertion. The macro puts that name in the
  original executable as an assertion string.
- Keep the node layout and stack padding. These are part of the matching build.

The cleanup was checked by compiling `build/GALE01/src/melee/lb/lbarq.o` with
the project's original compiler settings and comparing it byte for byte with
the object from the verified US v1.02 build.
