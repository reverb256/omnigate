# Cluster Transformation Plan

Generated: 2026-08-22T07:06:48.064780

## Execution Order


1. **sentry** (sequential)

   - Rollback barrier: `git-tag:sentry-pre-transform`

2. **nexus** (sequential)

   - Rollback barrier: `git-tag:nexus-pre-transform`

3. **zephyr, forge** (parallel)

   - Rollback barrier: `git-tag:{host}-pre-transform`


## Host Details


### zephyr (workstation)

- IP: 10.1.0.110

- Disk: nvme0n1

- Dependencies: sentry, nexus

- Parallel: forge


### nexus (k3s-server-builder)

- IP: 10.0.1.120

- Disk: nvme0n1

- Dependencies: sentry

- Parallel: none


### forge (mining-gpu)

- IP: 10.0.1.110

- Disk: nvme0n1

- Dependencies: sentry, nexus

- Parallel: zephyr


### sentry (control-plane)

- IP: 10.1.1.140

- Disk: nvme0n1

- Dependencies: none

- Parallel: none

