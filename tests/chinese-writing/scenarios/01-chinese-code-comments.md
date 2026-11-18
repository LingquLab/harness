# Clear Chinese Code Comments

## Skill Under Test

- `chinese-writing`

## Request

Rewrite this bilingual Host API comment for clarity. Keep behavior unchanged.

```cpp
// Destroy the opaque handle and coordinate internal resource cleanup.
// 销毁不透明句柄，协调资源清理。
void Destroy(Handle handle) {
    Cleanup(handle);
    ReleaseBuffer(handle);
}
```

## Expected Behavior

- Describe the cleanup call and subsequent buffer release shown by the implementation.
- Use `opaque handle` in Chinese and write each language in its natural order.
- Scan the revised Chinese draft and review any remaining matches in context.

## Failure Signals

- Replacing one forced technical translation with another.
- Leaving vague coordination language or adding an unsupported wait or success guarantee.
- Changing runtime behavior to match the rewritten comment.
