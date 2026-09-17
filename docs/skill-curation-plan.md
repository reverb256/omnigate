# Curated skill sets per host

## Host roles

| Host | Role | Focus |
|---|---|---|
| **Zephyr** | Authoring workstation | Dev, creative, writing, personal productivity, hermes mgmt |
| **Nexus** | Builder / storage / AI | Infra, build, CI/CD, AI/ML, storage, ops |
| **Sentry** | Control plane / monitoring | Infra, ops, security, cluster mgmt, nixos |
| **Forge** | Mining / gaming / media | GPU infra, mining ops, gaming, ComfyUI, media |

## Curated sets

### Zephyr (authoring) — ~120 skills

**Dev & Code**
bash-linux, git, github, github-actions-ci-fixes, github-issue-to-pr,
github-pr-workflow, github-code-review, github-repo-management, github-issues,
software-development, software-factory-operations, debugging,
improve-codebase-architecture, codebase-design, domain-modeling,
rust, async-python-patterns, python-performance-optimization,
fastapi-templates, api, web, frontend, frontend-ui-ux-engineer,
astro, astro-web-revival-deployment, vercel-react-best-practices,
tailwind-design-system, bubbletea, technical-clarity,
openspec-apply-change, openspec-archive-change, openspec-explore,
openspec-propose, openspec-sync-specs, to-spec, to-tickets,
planning, tmux, computer-use, serena-usage,
python-mcp-server-generator, mcp, mcp-builder, add-service-mcp,

**AI / ML / Compute**
mlops, mlops-engineer, llama-cpp-max-context-vulkan,
qwen-max-context-deployment, gguf-tensor-manifest-probe,
hermes-model-management, hermes-ram-protection,
deep-agents-memory, memory, memory-merger, machine-learning-engineer,

**Creative & Media**
creative, creative-portfolio-resume, generative-ui, top-design,
ai-image-generation, video-production, media, gifs, animate,
comfyui-inventory, comfyui-lora-training, comfyui-nodes-dev,
comfyui-prompt-engineer, comfyui-prompt-interview, comfyui-research,
comfyui-troubleshooter, comfyui-video-pipeline, comfyui-voice-pipeline,
comfyui-workflow-builder, scroll-storyteller,

**Writing & Marketing**
writing, site-agency, site-architecture, seo-audit, programmatic-seo,
sales-enablement, referral-program, paid-ads, analytics-tracking,
business-analyst, business-intelligence, changelog-automation,
documentation-last-reviewed-pattern, docs-for-agents, oo-documentation,
ux-writing, career, pricing-strategy, product-marketing-context,
project-manager, personal-productivity, note-taking, productivity,

**Hermes Self-Management**
hermes, hermes-bot-mode, hermes-cluster-upgrade, hermes-custom-providers,
hermes-desktop-plugins, hermes-live-session-intercom, hermes-plugin-management,
hermes-runtime-fixes, hermes-spoc-admin, hermes-themes, hermes-vault-access,
hermes-skill-migration, hermes-workspace-replacement,
a2a-token-troubleshooting, agent-dispatch, google-ai-hermes-integration,

**Infra (personal workstation)**
systemd-boot-optimization, zram-sizing, firewall-config, hardware-control,
tailscale-ssh, nix-build-capacity-policy, nix-remote-builds, nix-safe-build,
container-native, docker, network-engineer, dns, samsung-tv-remote-control,
hdr-enable-nixos, linux-hardening, security, security-best-practices,
homelab, infra, infrastructure, infrastructure-monitoring,

### Nexus (builder / storage / AI) — ~100 skills

**Infra & Boot**
systemd-boot-optimization, zram-sizing, firewall-config, hardware-control,
tailscale-ssh, nix-build-capacity-policy, nix-remote-builds, nix-safe-build,
container-native, docker, network-engineer, dns, linux-hardening,
security, security-best-practices, security-scanning-security-hardening,
homelab, infra, infrastructure, infrastructure-monitoring,
gpu-crash-debug, gpu-kubernetes-operations,

**NixOS & Build**
nixos, nixos-best-practices, nixos-cluster-deploy-ops, nixos-deploy,
nixos-deploy-verification, nixos-deprecation-fixes, nixos-desktop-entry-conflict,
nixos-developer, nixos-guard, nixos-secret-provisioning,
nixos-dendritic-registry-pattern, nixos-x86-64v3-overlay, nix-game-dev-env,
nix-rebuild-mcp, doc-maintenance-nixos, windows-gaming-vm-nixos,
nixos-cluster-maintenance-procedures, nixos-devenv-direnv-fix,
nixos-k8s-ai-infra-debugging, central-nixos-secret, drift-cleanup,
weekly-drift-scan, ghost-drive-os-migration, provision-nixos-server,
omnigate-migration-tool, cost-optimizer,

**Ops & Monitoring**
daily-oom-audit, oom-defense, secretspec-checkpoint, vaultwarden-sops-fix,
gha-runner-unstick, grafana, monitoring, monitoring-observability,
deployment-automation, devops, devops-automation, devops-debugging,
devops-rollout-plan, debugging, wayfinder, workflow, workflow-automation,
dogfood, grill-me,

**AI / ML / Storage**
mlops, mlops-engineer, llama-cpp-max-context-vulkan,
qwen-max-context-deployment, gguf-tensor-manifest-probe,
hermes-model-management, hermes-ram-protection,
deep-agents-memory, memory, memory-merger, machine-learning-engineer,

**Storage & Backup**
(uses storage-layer skills via sync.py, mount.py — not skill-based)

**Dev Tools**
bash-linux, git, github, github-actions-ci-fixes, software-development,
debugging, python-mcp-server-generator, mcp, mcp-builder,

### Sentry (control plane / monitoring) — ~80 skills

**Infra & Boot**
systemd-boot-optimization, zram-sizing, firewall-config, hardware-control,
tailscale-ssh, nix-build-capacity-policy, nix-remote-builds,
container-native, docker, network-engineer, dns, linux-hardening,
security, security-best-practices, security-scanning-security-hardening,
homelab, infra, infrastructure, infrastructure-monitoring,

**NixOS & Cluster**
nixos, nixos-best-practices, nixos-cluster-deploy-ops, nixos-deploy,
nixos-deploy-verification, nixos-deprecation-fixes, nixos-developer,
nixos-guard, nixos-secret-provisioning, nixos-dendritic-registry-pattern,
nix-rebuild-mcp, doc-maintenance-nixos, nixos-cluster-maintenance-procedures,
nixos-devenv-direnv-fix, nixos-k8s-ai-infra-debugging, central-nixos-secret,
drift-cleanup, weekly-drift-scan, ghost-drive-os-migration,
provision-nixos-server, omnigate-migration-tool, cost-optimizer,
cluster-conventions,

**Ops & Monitoring (core role)**
daily-oom-audit, oom-defense, secretspec-checkpoint, vaultwarden-sops-fix,
gha-runner-unstick, grafana, monitoring, monitoring-observability,
deployment-automation, devops, devops-automation, devops-debugging,
devops-rollout-plan, debugging, wayfinder, workflow, workflow-automation,
dogfood, grill-me, system-watchdog,

**Secrets**
agenix-secrets, encrypted-secrets, secretspec-checkpoint, vaultwarden-sops-fix,
central-nixos-secret,

**Dev Tools**
bash-linux, git, github, github-actions-ci-fixes, software-development,
debugging, python-mcp-server-generator, mcp,

### Forge (mining / gaming / media) — ~80 skills

**Infra & GPU**
systemd-boot-optimization, zram-sizing, firewall-config, hardware-control,
tailscale-ssh, nix-build-capacity-policy, nix-remote-builds,
container-native, docker, network-engineer, dns, linux-hardening,
security, security-best-practices, homelab, infra, infrastructure,
infrastructure-monitoring, gpu-crash-debug, gpu-kubernetes-operations,

**NixOS**
nixos, nixos-best-practices, nixos-cluster-deploy-ops, nixos-deploy,
nixos-deploy-verification, nixos-deprecation-fixes, nixos-developer,
nixos-guard, nixos-secret-provisioning, nixos-dendritic-registry-pattern,
nix-rebuild-mcp, doc-maintenance-nixos, nixos-cluster-maintenance-procedures,
nixos-devenv-direnv-fix, nixos-k8s-ai-infra-debugging, central-nixos-secret,
drift-cleanup, weekly-drift-scan, ghost-drive-os-migration,
provision-nixos-server, omnigate-migration-tool, cost-optimizer,

**Ops & Monitoring**
daily-oom-audit, oom-defense, secretspec-checkpoint, vaultwarden-sops-fix,
gha-runner-unstick, grafana, monitoring, monitoring-observability,
deployment-automation, devops, devops-automation, devops-debugging,
devops-rollout-plan, debugging, wayfinder, workflow, workflow-automation,
dogfood, grill-me, system-watchdog,

**Gaming / Media (core role)**
gaming, game-designer, game-ui-design, video-production, media,
social-media, social-media-download, social-content, gifs, animate,
comfyui-inventory, comfyui-lora-training, comfyui-nodes-dev,
comfyui-prompt-engineer, comfyui-prompt-interview, comfyui-research,
comfyui-troubleshooter, comfyui-video-pipeline, comfyui-voice-pipeline,
comfyui-workflow-builder, creative, generative-ui, scroll-storyteller,
top-design, ai-image-generation,

**Dev Tools**
bash-linux, git, github, github-actions-ci-fixes, software-development,
debugging, python-mcp-server-generator, mcp, computer-use,

## Deployment plan

1. On each host, `rm -rf ~/.hermes/skills/*`
2. Copy curated set from staging
3. Verify with `hermes skills list | wc -l`

## Skills to retire (not in any curated set)

- `ab-testing`, `ad-creative`, `ads`, `ai-research-explore`, `ai-seo`, `analytics`,
  `aso`, `churn-prevention`, `co-marketing`, `community-marketing`,
  `competitor-profiling`, `competitors`, `content-strategy`, `copy-editing`,
  `copywriting`, `cro`, `cua-driver`, `customer-research`, `directory-submissions`,
  `doc-maintenance`, `document-to-narration`, `emails`, `firecrawl-deep-research`,
  `flutter-apply-architecture-best-practices`, `flutter-build-responsive-layout`,
  `flutter-fix-layout-issues`, `free-tools`, `image`, `influencer-marketing`,
  `launch`, `lead-magnets`, `marketing-council`, `marketing-ideas`,
  `marketing-loops`, `marketing-plan`, `marketing-psychology`, `material-3`,
  `offers`, `onboarding`, `paywalls`, `plex`, `popups`, `pricing`,
  `product-marketing`, `prospecting`, `prowlarr`, `public-relations`,
  `qbittorrent`, `radarr`, `referrals`, `schema`, `seo-audit`, `signup`,
  `sms`, `smux`, `social`, `sonarr`, `svg-logo-designer`, `tui-design`,
  `video`, `writing-plans`, `yuanbao`, `apple`, `architecting-networks`,
  `akash`, `activepieces-expert`, `accessibility`, `ai-product-strategy`,
  `ai-inference-gateway-audit`, `ai-gateway-manager`, `agent-model-audit`,
  `billing-automation`, `blockchain`, `finance-expert`, `fund`, `feeds`,
  `email-sequence`, `emotional-narrative`, `echo-chamber-dev`, `drizzle-schema-fix`,
  `domain`, `domain-modeling`, `dramatic-2000ms-plus`, `diagramming`,
  `dataverse-python-advanced-patterns`, `dataverse-python-production-code`,
  `data-analysis`, `data-science`, `cost-optimizer`, `competitor-alternatives`,
  `communication`, `character-profile`, `capacity-planner`, `building-dashboards`,
  `bazarr`, `kanban-dispatcher-autoplay`, `k8s-cluster-conventions`,
  `k8s-manifest-workflows`, `k8s-mcp-troubleshooting`, `k8s-network-debugging`,
  `k8s-security`, `kubernetes`, `kubernetes-architect`, `kubernetes-specialist`,
  `kagent-a2a-troubleshooting`, `import-infrastructure-as-code`, `find-skills`,
  `free-tool-strategy`, `legal-risk-assessment`, `launch-strategy`,
  `leisure`, `red-teaming`, `referral-program`, `trovesandcoves-kanban-workflow`,
  `ux-writing`, `vercel-react-best-practices`, `web-design-guidelines`,
  `web-perf`, `workspace-dispatch`, `writing`, `okx-dex-swap`, `raydium`,
  `marginfi`, `namecheap-domains`, `n8n`, `kamino`, `jupiter`,
  `kelos-init-fix`, `kelos-model-auto-routing`, `kelos-task-notifications`,
  `kelos-verification-workflow`, `self-improving-agent`, `self-learning`,
  `stability-matrix`, `add-kelos-monitoring-to-astro`, `omniport`

Total retired: ~160 skills
