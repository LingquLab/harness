# Runtime Failure Triage

Preserve chronology and identify the first failing boundary. Paths and log formats vary by installation; discover them from the target process and metadata instead of assuming one global location.

## Minimal Evidence Packet

- target host/user, timestamp and timezone, process/device, exact command, exit status, and smallest reproducer;
- CANN component, driver, firmware, custom-operator package, framework, and application build identities with source paths;
- exact API return and immediate recent-error text when supported;
- bounded application stderr, plog/device-log window, and read-only device status around the event;
- invocation path, inputs, shapes/types/formats, TilingKey, `blockDim`, workspace, stream, and synchronization boundary.

Do not collect the entire home directory or all historical logs. Prefer a narrow time/PID/device window, cap bytes and lines before rendering, and redact secrets.

## Failure Routing

### Return Code or Recent Error

Map the first non-success return using target-version evidence, then find the first related plog `ERROR` in the same time, process, and device window. A later synchronization or cleanup error must not replace that first failure.

### Kernel or Operator Not Found

Trace public operator name, registration/package metadata, custom OPP search paths, selected vendor directory, architecture, compiled Kernel name, file existence, permissions, loader dependencies, and process environment. Prove which artifact the failing process loaded; do not repair by deleting caches or reinstalling blindly.

### Inference or Tiling Failure

Capture concrete descriptors/attributes, `OpDef` and inference contract, Tiling entry status, checked shape products, capacity query, serialized size, selected TilingKey, `blockDim`, and workspace. Reject silent fallback to a key or tile that cannot satisfy the input.

### Launch or Device Exception

Match caller arguments and address spaces to the Kernel ABI and binary variant. Check GM/UB/workspace bounds, alignment, tails, supported API/type/SoC, queue/tensor lifetime, barrier participation, and asynchronous lifetimes. Synchronize only at a controlled diagnostic boundary to associate the asynchronous failure with a launch.

### Hang or Timeout

Distinguish host wait, stream/device wait, missing event, divergent barrier, producer-consumer mismatch, infinite loop, collective mismatch, and resource starvation. Capture bounded process/device state before considering an invasive debugger or reset. Never terminate another workload or reset a shared device without explicit authority.

### Crash

Preserve exit signal, application stack/core metadata when already available, last API boundary, lifetime/cleanup order, loader provenance, and device exception context. Do not enable core dumps or attach a debugger on a production/shared process without impact approval.

## Closing the Loop

The root cause is closed only when one concrete condition explains the first failure, a minimal change removes that condition, and the original reproducer plus relevant boundary tests pass at the required evidence level.
