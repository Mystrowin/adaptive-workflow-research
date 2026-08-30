# Security and privacy

Generated code is untrusted. The benchmark verifier uses a pinned local
container with no network, read-only root, dropped capabilities, an
unprivileged user, a task-only temporary filesystem, a process limit, timeout,
memory limit, and one verifier worker. Host-shell verification is not part of
the intended protocol.

The public repository is an allowlisted projection. It excludes credentials,
tokens, cookies, browser profiles, SSH material, private prompts, generated
programs, private logs, model files, raw benchmark tasks, local usernames,
home-directory paths, and private project files. The included source snapshot
contains benchmark safety logic but not private runtime state.

Run python analysis/run_checks.py before sharing a copy. It scans the
publication repository for credential-shaped values and local paths, verifies
the sanitized export safety report, and fails closed on a match. Nothing in
the repository uploads or publishes itself.
