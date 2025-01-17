# The Merge -- Honest Validator

**Notice**: This document is a work-in-progress for researchers and implementers.

## Table of contents

<!-- TOC -->
<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Introduction](#introduction)
- [Prerequisites](#prerequisites)
- [Custom types](#custom-types)
- [Helpers](#helpers)
  - [`get_pow_block_at_terminal_total_difficulty`](#get_pow_block_at_terminal_total_difficulty)
  - [`get_terminal_pow_block`](#get_terminal_pow_block)
  - [`get_payload_id`](#get_payload_id)
- [Protocols](#protocols)
  - [`ExecutionEngine`](#executionengine)
    - [`get_payload`](#get_payload)
- [Beacon chain responsibilities](#beacon-chain-responsibilities)
  - [Block proposal](#block-proposal)
    - [Constructing the `BeaconBlockBody`](#constructing-the-beaconblockbody)
      - [ExecutionPayload](#executionpayload)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->
<!-- /TOC -->

## Introduction

This document represents the changes to be made in the code of an "honest validator" to implement executable beacon chain proposal.

## Prerequisites

This document is an extension of the [Altair -- Honest Validator](../altair/validator.md) guide.
All behaviors and definitions defined in this document, and documents it extends, carry over unless explicitly noted or overridden.

All terminology, constants, functions, and protocol mechanics defined in the updated Beacon Chain doc of [The Merge](./beacon-chain.md) are requisite for this document and used throughout.
Please see related Beacon Chain doc before continuing and use them as a reference throughout.

## Custom types

| Name | SSZ equivalent | Description |
| - | - | - |
| `PayloadId` | `Bytes8` | Identifier of a payload building process |

## Helpers

### `get_pow_block_at_terminal_total_difficulty`

```python
def get_pow_block_at_terminal_total_difficulty(pow_chain: Dict[Hash32, PowBlock]) -> Optional[PowBlock]:
    # `pow_chain` abstractly represents all blocks in the PoW chain
    for block in pow_chain:
        parent = pow_chain[block.parent_hash]
        block_reached_ttd = block.total_difficulty >= TERMINAL_TOTAL_DIFFICULTY
        parent_reached_ttd = parent.total_difficulty >= TERMINAL_TOTAL_DIFFICULTY
        if block_reached_ttd and not parent_reached_ttd:
            return block

    return None
```

### `get_terminal_pow_block`

```python
def get_terminal_pow_block(pow_chain: Dict[Hash32, PowBlock]) -> Optional[PowBlock]:
    if TERMINAL_BLOCK_HASH != Hash32():
        # Terminal block hash override takes precedence over terminal total difficulty
        if TERMINAL_BLOCK_HASH in pow_chain:
            return pow_chain[TERMINAL_BLOCK_HASH]
        else:
            return None

    return get_pow_block_at_terminal_total_difficulty(pow_chain)
```

### `get_payload_id`

Given the `head_block_hash` and the `payload_attributes` that were used to
initiate the build process via `notify_forkchoice_updated`, `get_payload_id()`
returns the `payload_id` used to retrieve the payload via `get_payload`.

```python
def get_payload_id(parent_hash: Hash32, payload_attributes: PayloadAttributes) -> PayloadId:
    return PayloadId(
        hash(
            parent_hash
            + uint_to_bytes(payload_attributes.timestamp)
            + payload_attributes.random
            + payload_attributes.fee_recipient
        )[0:8]
    )
```

*Note*: This function does *not* use simple serialize `hash_tree_root` as to
avoid requiring simple serialize hashing capabilities in the Execution Layer.

## Protocols

### `ExecutionEngine`

*Note*: `get_payload` function is added to the `ExecutionEngine` protocol for use as a validator.

The body of this function is implementation dependent.
The Engine API may be used to implement it with an external execution engine.

#### `get_payload`

Given the `payload_id`, `get_payload` returns the most recent version of the execution payload that
has been built since the corresponding call to `notify_forkchoice_updated` method.

```python
def get_payload(self: ExecutionEngine, payload_id: PayloadId) -> ExecutionPayload:
    """
    Return ``execution_payload`` object.
    """
    ...
```

## Beacon chain responsibilities

All validator responsibilities remain unchanged other than those noted below. Namely, the transition block handling and the addition of `ExecutionPayload`.

### Block proposal

#### Constructing the `BeaconBlockBody`

##### ExecutionPayload

To obtain an execution payload, a block proposer building a block on top of a `state` must take the following actions:

1. Set `payload_id = prepare_execution_payload(state, pow_chain, finalized_block_hash, fee_recipient, execution_engine)`, where:
    * `state` is the state object after applying `process_slots(state, slot)` transition to the resulting state of the parent block processing
    * `pow_chain` is a `Dict[Hash32, PowBlock]` dictionary that abstractly represents all blocks in the PoW chain with block hash as the dictionary key
    * `finalized_block_hash` is the hash of the latest finalized execution payload (`Hash32()` if none yet finalized)
    * `fee_recipient` is the value suggested to be used for the `coinbase` field of the execution payload


```python
def prepare_execution_payload(state: BeaconState,
                              pow_chain: Dict[Hash32, PowBlock],
                              finalized_block_hash: Hash32,
                              fee_recipient: ExecutionAddress,
                              execution_engine: ExecutionEngine) -> Optional[PayloadId]:
    if not is_merge_complete(state):
        is_terminal_block_hash_set = TERMINAL_BLOCK_HASH != Hash32()
        is_activation_epoch_reached = get_current_epoch(state.slot) < TERMINAL_BLOCK_HASH_ACTIVATION_EPOCH
        if is_terminal_block_hash_set and is_activation_epoch_reached:
            # Terminal block hash is set but activation epoch is not yet reached, no prepare payload call is needed
            return None

        terminal_pow_block = get_terminal_pow_block(pow_chain)
        if terminal_pow_block is None:
            # Pre-merge, no prepare payload call is needed
            return None
        # Signify merge via producing on top of the terminal PoW block
        parent_hash = terminal_pow_block.block_hash
    else:
        # Post-merge, normal payload
        parent_hash = state.latest_execution_payload_header.block_hash

    # Set the forkchoice head and initiate the payload build process
    payload_attributes = PayloadAttributes(
        timestamp=compute_timestamp_at_slot(state, state.slot),
        random=get_randao_mix(state, get_current_epoch(state)),
        fee_recipient=fee_recipient,
    )
    execution_engine.notify_forkchoice_updated(parent_hash, finalized_block_hash, payload_attributes)
    return get_payload_id(parent_hash, payload_attributes)
```

2. Set `block.body.execution_payload = get_execution_payload(payload_id, execution_engine)`, where:

```python
def get_execution_payload(payload_id: Optional[PayloadId], execution_engine: ExecutionEngine) -> ExecutionPayload:
    if payload_id is None:
        # Pre-merge, empty payload
        return ExecutionPayload()
    else:
        return execution_engine.get_payload(payload_id)
```

*Note*: It is recommended for a validator to call `prepare_execution_payload` as soon as input parameters become known,
and make subsequent calls to this function when any of these parameters gets updated.
