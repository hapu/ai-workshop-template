# Proposal Application Safety Design

**Status:** Implemented on `main` by PR #26; crash-injection and adversarial tests passed CI on Python 3.10–3.13  
**Decision date:** 2026-11-23  
**Scope:** Local application of staged browser-assistant file proposals  
**Selected platform:** POSIX  
**Selected recovery policy:** Roll back interrupted transactions  
**Parent-directory policy:** Existing directories only  
**Approval policy:** Interactive, digest-bound confirmation

## 1. Purpose, implementation status, and non-goals

This document records the approved safety contract and the implementation now available in `main`. The implementation was promoted by [PR #26](https://github.com/hapu/ai-workshop-template/pull/26); its required CI workflow passed on Python 3.10–3.13 in [run #158](https://github.com/hapu/ai-workshop-template/actions/runs/45327477908).

The workflow remains separated into distinct stages:

- Import parses an untrusted, bounded JSON bundle.
- Staging validates proposal structure, repository-relative paths, protected paths, expected hashes, and repository identity.
- Preview rechecks current preconditions and recomputes a read-only diff from the live snapshot.
- Apply requires a full staged-record digest and exact interactive confirmation, then performs journaled file operations with verification and rollback.
- Recovery inventories an interrupted transaction and requires a separate exact confirmation bound to the journal digest.

The subsystem does not execute shell commands, invoke providers, install packages, or perform Git commits, pushes, pull requests, or merges. Those actions remain separate workflows and approvals.

The implementation provides recoverable multi-file application, not instantaneous multi-file atomic visibility to arbitrary external readers.

## 2. Accepted decisions

| Decision | Selected behavior |
| --- | --- |
| Platform | POSIX first. Require the filesystem primitives described below; fail closed if unavailable. |
| Interrupted transaction | Roll back to the pre-transaction state by default. |
| Missing parent directories | Reject. Every parent directory must already exist. |
| Approval | Interactive confirmation bound to the full staged-record SHA-256 digest. No non-interactive apply mode. |

The initial implementation should target the repository's supported POSIX/Linux development environment. Windows is unsupported for apply; staging and preview may remain available there.

## 3. Trust boundaries and threat model

Proposal bundles, their source labels, file contents, paths, and provenance fields are untrusted input. A staged checksum detects accidental corruption but is not an identity signature: a party able to edit a staged record can recompute an unkeyed checksum.

The design protects against:
- stale proposals and changes between staging, review, and application;
- path traversal, symlink traversal, and non-regular target objects;
- concurrent cooperating workshop processes;
- process termination or power loss at defined transaction boundaries;
- accidental or unexpected filesystem states during rollback.

The design does not claim protection against:
- a malicious process running as the same user that deliberately ignores advisory locks and races filesystem operations;
- root or another principal with equivalent permissions modifying the repository or private state;
- storage hardware, filesystem, or kernel failures that violate reported durability;
- preservation of every filesystem metadata feature (for example, arbitrary ACLs, extended attributes, or ownership changes).

POSIX advisory locks coordinate cooperating workshop processes; they do not lock out editors or arbitrary programs. Hash and object-identity checks are therefore still required. The implementation must document residual races that cannot be eliminated portably with Python's standard library.

## 4. Exact approval contract

### 4.1 Digest being approved

The approval digest is the full lowercase SHA-256 value already represented by the staged record's `record_sha256` field. It is computed over canonical JSON for the complete staged record with only the `record_sha256` field omitted. This binds approval to the proposal ID, operations, paths, contents, preconditions, provenance, and stored previews.

The digest is an approval identifier, not proof of who authored the proposal. The apply command must independently recompute it from the record read from private staging; it must not trust a supplied digest or the stored checksum by itself.

### 4.2 Interactive flow

Proposed CLI shape:

```sh
python3 -m workshop proposal preview PROPOSAL_ID --project .

python3 -m workshop proposal apply PROPOSAL_ID \
  --approve-sha256 FULL_64_CHARACTER_DIGEST \
  --project .
```

The apply command must:
1. Require a terminal for confirmation; reject non-interactive stdin.
2. Acquire the proposal and repository locks before final review and confirmation.
3. Re-read the staged record using safe private-state path handling; validate its schema, proposal ID, record checksum, and canonical digest.
4. Require the supplied full digest to match the recomputed digest using a constant-time comparison.
5. Revalidate the repository identity, every operation path, and every target precondition.
6. Display operation list, digest, and diffs recomputed from the live snapshot (never trust stored preview text), then require the exact line `APPLY PROPOSAL_ID FULL_64_CHARACTER_DIGEST`.
7. Re-read the staged record and revalidate target snapshots after confirmation.
8. Persist a durable transaction journal before the first repository modification.

No approval is inferred from import, preview, a previous command, or a previous proposal. No abbreviated digest, default confirmation, wildcard, or remembered approval is accepted. Any change to the staged record invalidates the supplied digest. A successful committed transaction cannot be applied again; restaging is required for a new proposal. A rolled-back proposal requires a fresh interactive approval for any retry.

The confirmation is consumed by the single transaction attempt. Recovery is a separate command and must not reuse the original apply approval.

## 5. Repository identity and path safety

### 5.1 Repository binding

At staging time, record a repository identity containing at least:
- canonical absolute repository-root path;
- root directory device and inode values (`st_dev`, `st_ino`).

Staged-record version 2 contains this identity and includes it in the record digest. The incoming proposal-bundle version remains independent from the staged-record version. Existing staged records without repository identity remain previewable but are not eligible for application; users must restage them.

At apply and recovery time, open the root directory and compare its identity with the recorded values. Reject a moved, replaced, or different root. This is a local filesystem identity check, not a cryptographic repository identity.

The repository root must be an existing directory and must not itself be a symlink. The private `.workshop` state directory must be verified separately and must not be reached through a symlink.

### 5.2 Descriptor-relative traversal

Do not rely on `Path.resolve()`, `is_symlink()`, or a path check followed by an ordinary path-based open as the final security boundary.

On POSIX, use directory file descriptors:
- Open the repository root once with directory and close-on-exec flags.
- Traverse each existing parent component relative to the verified parent descriptor using `os.open()` with `O_DIRECTORY` and `O_NOFOLLOW`.
- Verify each opened component with `fstat()`.
- Open targets relative to the verified parent descriptor with `O_NOFOLLOW`; verify regular-file type with `fstat()`.
- Use descriptor-relative rename, link, and unlink operations where supported.
- Retain relevant descriptors through the operation so path traversal does not restart from an untrusted absolute path.

At startup, verify that the required POSIX flags and Python `dir_fd` operations are available. If a required primitive is absent, fail closed with a clear unsupported-platform error.

### 5.3 Path and object policy

Reapply all staging restrictions at apply time:
- canonical repository-relative POSIX paths only;
- no empty, dot, parent, absolute, drive-prefixed, or backslash path components;
- no duplicate targets (case-insensitive duplicate rejection remains);
- no protected Git/workshop metadata, credentials, secrets, or protected automation paths;
- no symlink in any parent component or at the target;
- no FIFO, socket, device, directory, or other non-regular target;
- reject existing targets with `st_nlink > 1` in the initial implementation;
- parent directories must already exist and must be ordinary directories.

For `create`, the destination must be absent. For `update` and `delete`, it must be a regular file whose bytes match the expected SHA-256. Recheck file type, identity, size limits, and digest after opening the file descriptor; do not hash a separately resolved path and then open it again.

Do not create missing parent directories. Do not follow or repair symlinks.

## 6. Concurrency control

Use two OS-managed advisory locks, both held from final review through transaction completion or recovery:

1. **Proposal lock:** serializes apply and recovery for one proposal.
2. **Repository transaction lock:** serializes all workshop proposal transactions for the same repository.

Use POSIX `fcntl.flock` on lock files in the verified private workshop state directory. Open lock files with no-follow protections, verify they are regular files owned by the current user, and keep their descriptors open for the entire critical section. Use a bounded wait and report timeout without modifying targets. Acquire locks in one documented global order: proposal lock, then repository lock.

Do not use PID-only stale-lock deletion. The OS releases an advisory lock when its owning descriptors/process close. Lock files may remain on disk; their existence alone does not mean the lock is held.

These locks only coordinate workshop processes. External editors and programs may ignore them; immediate precondition checks and post-operation verification remain mandatory.

## 7. Transaction storage and journal

Store transaction state under the private proposal directory:

```text
.workshop/
  proposals/
    PROPOSAL_ID/
      proposal.json
      transactions/
        TRANSACTION_ID/
          journal.json
          backups/
            0001.bin
            0002.bin
          prepared/
            0001.bin
            0002.bin
```

Use mode `0700` for private directories and `0600` for private files. Verify ownership and reject symlinks in every private-state path component. Never store credentials, tokens, shell commands, or executable proposal content in the journal.

Before the first repository modification, prepare and durably flush:
- a backup of every existing target's original bytes;
- a prepared file for every create/update operation;
- original and proposed SHA-256 digests;
- operation order, paths, operation types, and expected preconditions;
- repository identity and proposal digest;
- transaction ID, format/version, and state.

The journal is canonical, versioned JSON with its own integrity digest. It is an integrity check, not an authenticity signature. Journal writes use a temporary file in the same private directory, file flush plus `fsync`, atomic replacement, and parent-directory `fsync`. The implementation must define and test the behavior on filesystems where directory `fsync` is unsupported; it must not silently claim stronger durability than the platform provides.

Keep backups until the transaction is durably committed and verified. Do not prune recovery data automatically while a transaction is incomplete or marked as requiring recovery.

## 8. Transaction protocol

### 8.1 Preparation (no repository targets changed)

1. Acquire proposal and repository locks.
2. Validate staged-record checksum, proposal digest, proposal schema, and repository identity.
3. Revalidate all operation paths and expected target states.
4. Read and hash original file bytes through verified descriptors.
5. Prepare every replacement/create payload in private transaction storage.
6. Back up every existing update/delete target; record original digest and required basic mode information.
7. Flush all backup and prepared files; flush their directories.
8. Write and durably flush the complete journal in state `PREPARED`.
9. Obtain the exact interactive approval described in section 4, after displaying the operation summary.
10. Revalidate all target preconditions immediately before starting writes.
11. Persist journal state `APPLYING`.

No repository target may change before the durable `APPLYING` state exists.

### 8.2 Applying operations

Apply operations in proposal order. For each operation, record intent and completion in the journal and flush journal updates around the filesystem transition.

- **Create:** install a fully prepared sibling file with an atomic no-overwrite operation. A POSIX hard-link operation from a prepared sibling to the destination can provide create-if-absent semantics; unlink the temporary name after verifying the installed file. Do not use a check-then-open sequence that can overwrite a file created concurrently.
- **Update:** create a same-directory hard link from the current regular target to a uniquely named quarantine entry using descriptor-relative, no-follow link semantics. Verify the linked object identity, digest, and expected link count; unlink the original target name only after verification. Install prepared content at the target with no-overwrite hard-link semantics. If installation fails, restore the quarantined original only if the target name remains absent.
- **Delete:** create and verify the same-directory quarantine hard link, then unlink the original target name only after identity, digest, and link-count checks. Keep the quarantine entry until commit is durable.

Same-directory hard-link quarantine avoids cross-filesystem rename and gives the transaction an object it can inspect before removing the original name. The durable private backup remains the recovery source. Temporary/quarantine names are derived from the random transaction ID and operation index, collision-checked, recorded in the journal, and created only within the verified parent directory. Filesystems that do not support the required no-follow hard-link operation fail closed.

After each operation:
- verify the target's resulting state using a no-follow descriptor and expected digest (or absence for delete);
- flush the affected file and parent directory where applicable;
- persist the operation completion in the journal.

If a target name is unexpectedly occupied, a moved object has the wrong identity/hash, or any verification fails, stop. Do not overwrite the unexpected object. Attempt rollback only when the observed state is unambiguous; otherwise enter `NEEDS_RECOVERY`.

### 8.3 Commit

After every operation is verified:
1. Persist and flush journal state `COMMITTED`.
2. Only after the commit marker is durable, remove same-directory quarantine entries and temporary names.
3. Flush affected parent directories.
4. Retain a compact transaction record sufficient to prevent replay and explain the result. Backups may be removed only after commit durability and cleanup are confirmed.

A crash after the durable commit marker is a committed transaction; recovery performs cleanup, not rollback.

## 9. Recovery and rollback

Proposed command:

```sh
python3 -m workshop proposal recover TRANSACTION_ID
```

Recovery is a separate operation. It acquires the same locks, validates the journal and repository identity, inventories every target/quarantine/temp object, and prints a recovery preview before asking the user to type the exact line `ROLLBACK TRANSACTION_ID FULL_64_CHARACTER_JOURNAL_SHA256`. The journal digest is recomputed from the canonical journal with its digest field omitted. Non-interactive recovery is rejected. Cleanup after a durably committed transaction may use the same explicit recovery command but must clearly report that it is cleanup-only, not rollback.

Default policy is rollback for any valid incomplete transaction. Do not resume forward application automatically.

### 9.1 State model

| State | Meaning |
| --- | --- |
| `PREPARING` | Private backups/prepared files being built; no target writes allowed. |
| `PREPARED` | All required private data and journal are durable; no target writes yet. |
| `APPLYING` | Target operations may be partially applied. |
| `COMMITTED` | All operations verified and commit marker durably written. |
| `ROLLING_BACK` | Rollback is in progress and journaled. |
| `ROLLED_BACK` | Original target state restored and verified. |
| `NEEDS_RECOVERY` | Observed state is ambiguous or unsafe for automatic modification. |

A crash in `PREPARING` or `PREPARED` requires no target rollback because the protocol forbids target writes before `APPLYING`. Remove incomplete private preparation only after validating that no target operation occurred and no unexpected objects exist. A crash in `APPLYING` or `ROLLING_BACK` requires inventory and rollback. A crash in `COMMITTED` requires cleanup only.

### 9.2 Idempotent rollback rules

Infer actual state from target contents, hashes, and recorded quarantine identities; do not trust the last journal operation flag alone.

- **Original file already present and matching:** leave it unchanged.
- **Updated target matches the transaction's proposed digest:** remove/rename it only as required to restore the original backup, and only after verifying the exact object.
- **Created target matches the transaction's proposed digest:** remove it; otherwise stop.
- **Deleted target is absent and its verified backup is available:** restore with a no-overwrite installation.
- **Quarantine entry matches the recorded original object:** restore it only if the destination name is absent.
- **Any target or quarantine entry has unexpected content or identity:** do not overwrite or delete it; mark `NEEDS_RECOVERY`.

Rollback itself is journaled and idempotent. After every restoration/removal, verify the resulting state and flush the affected directory. A second crash during rollback must be safely inspectable and resumable.

Never overwrite an unexpected external modification. If restoration cannot proceed without overwriting an occupied path, stop and require manual resolution. Preserve all remaining backups and journal data in `NEEDS_RECOVERY`.

## 10. Durability and filesystem limitations

A sequence of per-file atomic operations is not a globally atomic multi-file commit. Other processes that do not honor the workshop lock may observe intermediate states. A crash can also occur between any two operations.

The design therefore guarantees, within the stated platform/filesystem assumptions:
- no target write before complete private preparation and a durable journal;
- atomic visibility of each individual installed file where the selected primitive provides it;
- detection of stale or unexpected file states;
- rollback of known partial states without overwriting unexpected content;
- explicit manual-recovery state when safe automatic restoration cannot be proven.

It does not promise that an external observer sees all files change at once, nor that a malicious same-user process cannot race advisory-lock holders. Use a clean working tree and avoid concurrent external edits during apply.

## 11. Error handling and user reporting

Every failure must return a nonzero exit status and identify whether:
- no repository targets were changed;
- rollback completed and verified;
- the transaction committed;
- manual recovery is required.

Never report success solely because a write syscall returned successfully. Verify resulting hashes and durable transaction state.

Do not delete backups, journals, quarantine entries, or unexpected files to make a failed transaction appear clean.

## 12. Module boundaries

Keep `workshop/proposals.py` responsible for untrusted bundle parsing, staging, and read-only preview. Put apply-specific code in a separate package:

```text
workshop/proposal_apply/
  __init__.py
  approval.py       # digest verification and interactive confirmation
  filesystem.py     # POSIX dirfd traversal and safe file primitives
  locking.py        # proposal and repository advisory locks
  journal.py        # durable versioned transaction records
  transaction.py    # preparation, apply, verification, commit
  recovery.py       # inventory, preview, rollback, cleanup
```

No module may invoke a shell, provider adapter, package manager, or Git write operation.

## 13. Required test plan and acceptance criteria

### Approval
- Wrong proposal ID, wrong digest, truncated digest, and changed staged record are rejected.
- A recomputed staged checksum does not bypass the user's independently supplied digest.
- Missing confirmation, altered confirmation text, and non-interactive stdin are rejected.
- A committed transaction cannot be replayed.
- A rolled-back retry requires fresh interactive approval.

### Filesystem and path safety
- Symlinks at every parent level and at the target are rejected.
- Directory/regular-file substitution and target replacement races are detected by post-transition identity/hash checks.
- Hard-linked targets, special files, protected paths, and missing parent directories are rejected.
- Create never overwrites a destination that appears concurrently.
- All target reads and mutations use verified directory descriptors and no-follow semantics.

### Concurrency
- Two processes cannot apply/recover the same proposal concurrently.
- Two proposals cannot transact concurrently in the same repository.
- Lock timeout leaves repository targets unchanged.
- Process termination releases OS-managed locks.
- Tests demonstrate and document that non-cooperating external writers are outside the advisory-lock guarantee.

### Crash and recovery
Inject process termination after each durable journal transition and each filesystem operation, including preparation, quarantine, installation, delete, verification, commit marker, cleanup, and every rollback step.

Acceptance criteria:
1. Every successfully recovered transaction ends in a verified original state or a verified committed state.
2. Any unexpected content/identity causes `NEEDS_RECOVERY`; it is never silently overwritten or removed.
3. Recovery is idempotent across repeated interruptions.
4. Backups and journals remain available until a terminal state is durably verified.
5. Unit tests cover create, update, delete, mixed multi-file proposals, disk/write failures, and recovery failures.

The test suite must run on each supported Python version in CI. The implementation must not claim stronger guarantees than the tested OS/filesystem combinations provide.

## 14. Implementation history and acceptance

The design was approved on 2026-11-23 with the decisions recorded in section 2. Implementation proceeded in separately reviewable stages:

1. POSIX filesystem primitives and advisory-lock tests.
2. Canonical journals, private backup/prepared-file creation, lock-held snapshots, and recovery inventory.
3. Interactive digest-bound approval, repository-bound staged records, journaled create/update/delete application, verification, automatic rollback, and explicit recovery/cleanup commands.
4. Adversarial path/race, concurrency, rollback-idempotency, and process-crash/recovery tests.
5. Documentation and repository CI validation.

The implementation was promoted to `main` by [PR #26](https://github.com/hapu/ai-workshop-template/pull/26). The promotion workflow [run #158](https://github.com/hapu/ai-workshop-template/actions/runs/45327477908) completed successfully. The merge commit records that crash-injection and adversarial tests passed on Python 3.10–3.13. The current CLI exposes separate `proposal apply` and `proposal recover` commands. Import and preview remain read-only; application remains POSIX-only and interactive.

The test plan above remains the regression contract for future changes. Any change to filesystem primitives, journal transitions, rollback, or recovery must preserve these acceptance properties and pass the supported Python CI matrix before merge.
