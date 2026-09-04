# Persistent Shell Design

## Scope

`pshell` is a user-level Windows CLI backed by a detached local daemon. PowerShell and Git Bash launchers call the same Python client. The daemon keeps Paramiko SSH transports and long-running non-interactive shell channels alive so separate invocations reuse the same remote shell. It supports OpenSSH aliases plus direct `[user@]host` targets, key or agent authentication, multiple targets, persistent shell state, command timeouts, status, and explicit shutdown.

It does not implement interactive terminal applications, passwords, proxy jumps, port forwarding, file transfer, binary-clean output, or concurrent commands within one shell.

## Local Protocol

The daemon listens only on `127.0.0.1` at an operating-system-selected port. `%LOCALAPPDATA%\pshell\daemon.json` contains its PID, port, and a randomly generated bearer token. Each request and response is one size-bounded UTF-8 JSON line. The inherited user-profile ACL is the first boundary; the token is the second. The daemon rejects non-loopback clients and invalid tokens.

The client authenticates a short, bounded `ping` against recorded state and replaces stale state when it starts a daemon. A detached daemon starts only on demand. Concurrent cold-start callers coordinate through an operating-system file lock; the lock holder rechecks state before launching and publishes a reachable daemon before releasing the lock. Daemon shutdown uses the same lock for its ownership check and state cleanup, so an exiting daemon cannot remove a replacement daemon's state. The lock does not cover SSH session creation or command execution, so separate targets retain their normal concurrency. `pshell daemon-stop` closes every SSH session, removes daemon state, and terminates the daemon.

## Remote Framing

Each target owns a Paramiko client, long-running non-interactive shell channel, generation counter, and mutex. The channel starts a clean Bash when available and falls back to `sh`; it does not allocate a PTY or run prompt hooks. For every command the daemon appends a cryptographically random marker which prints the command exit status. Bytes received before that marker are returned as combined output.

Only one command may be outstanding in a shell. A timeout, closed channel, malformed marker, or transport failure closes the channel. A later request reconnects with a higher generation and returns `state_reset: true`; commands are never replayed automatically.

## SSH Resolution And Trust

Target lookup reads `%USERPROFILE%\.ssh\config` with Paramiko's OpenSSH parser when a session is first started. Later commands use the retained resolved target and do not parse configuration again. Explicit CLI user, port, and identity values override config values. Supported config fields are `HostName`, `User`, `Port`, `IdentityFile`, `ConnectTimeout`, and `ServerAliveInterval`. Proxy commands and jump hosts are rejected rather than partially honored.

The client loads `%USERPROFILE%\.ssh\known_hosts`. A new host key is accepted on first use and atomically appended without rewriting existing comments or entries. A changed key is rejected. Authentication uses the configured identity, Paramiko-supported default keys, or an available agent; passwords never cross the local protocol.

## Validation Boundary

Local validation covers argument parsing, single-daemon cold start under concurrent callers, platform lock selection, daemon lifecycle, token rejection, stale-state cleanup, and status commands. Platform lock tests mock the Windows API selection; a live Windows run is still required to validate actual `msvcrt` lock behavior. Live validation must separately demonstrate first-use persistence or retained-key verification, command output and exit status, state persistence (`cd` followed by `pwd`), multiple commands on one generation, timeout invalidation, explicit stop, and materially lower steady-state latency. Results apply only to the tested client, server, authentication path, and shell.
