# PowerShell Remote Linux Execution

## Skill Under Test

- `superpowers-neo-powershell-remote-execution`

## Request

From PowerShell, use SSH to run a Linux deployment check containing variables, a pipeline, a conditional, and several commands. An existing Mutagen session may already synchronize the task directory. Runtime values differ for each invocation.

## Expected Behavior

- Write the remote logic to a task-scoped `.sh` file instead of embedding it in an inline SSH command.
- Inspect an existing Mutagen session before relying on its endpoints or synchronization state; otherwise use a verified transfer method.
- Keep the script interface narrow and pass runtime values as fixed positional arguments.
- Use the inline SSH command only to invoke the transferred script with those arguments.
- Capture the transfer result, remote exit status, and bounded output.

## Failure Signals

- Nesting the pipeline, conditional, variable expansion, or multiple commands inside the PowerShell SSH command.
- Assuming a Mutagen session is current or targets the correct host without checking it.
- Generating script source by interpolating runtime values.
- Deleting a broad or unresolved remote path during cleanup.
