G1: sshd baseline uniform on all fleet hosts  |  CHECK: bash /home/j_kro/Work/Projects/omarchy-migrate/fleet-ssh/scripts/gates-run.sh G1  |  EXPECT: BASELINE-OK
G2: restart-forever drop-in active on all hosts  |  CHECK: bash /home/j_kro/Work/Projects/omarchy-migrate/fleet-ssh/scripts/gates-run.sh G2  |  EXPECT: RESTART-OK
G3: fleet key byte-identical on all hosts  |  CHECK: bash /home/j_kro/Work/Projects/omarchy-migrate/fleet-ssh/scripts/gates-run.sh G3  |  EXPECT: KEY-OK
G4: client ssh config identical on all hosts  |  CHECK: bash /home/j_kro/Work/Projects/omarchy-migrate/fleet-ssh/scripts/gates-run.sh G4  |  EXPECT: CONFIG-OK
G5: full connectivity matrix incl. windows rigs  |  CHECK: bash /home/j_kro/Work/Projects/omarchy-migrate/fleet-ssh/scripts/gates-run.sh G5  |  EXPECT: MATRIX-OK 15/15
G6: miner plugin consumers reach every host  |  CHECK: bash /home/j_kro/Work/Projects/omarchy-migrate/fleet-ssh/scripts/gates-run.sh G6  |  EXPECT: CONSUMERS-OK
G7: tailscale ssh state matches the safe documented state  |  CHECK: bash /home/j_kro/Work/Projects/omarchy-migrate/fleet-ssh/scripts/gates-run.sh G7  |  EXPECT: TS-STATE-OK
