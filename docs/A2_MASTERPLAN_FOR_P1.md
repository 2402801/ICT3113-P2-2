# A2 Masterplan for P1 (SUT laptop)

From P2 (load generator). Read this top to bottom. Details are in `docs/A2_P1_P2_GUIDE.md`.

**Decision: we run WITHOUT the thinking-off configurations. Total = 9 speed runs.**

## 1. Roles
| | P1 (you) | P2 |
|---|---|---|
| Laptop | Official SUT: Docker, Ollama, gemma, server | Load generator: JMeter only |
| Never do | - | Run the model |
| Owns | S measurement, settings, runs, logs | Workload, JMeter, .jtl files |

## 2. What S is
- S = middle time (seconds) of 3 different typical tickets sent to **gemma4:e4b alone, thinking on**, measured on YOUR laptop.
- Arrival rate = 1 ticket per 2S s (`3600 / 2S` per hour).
- Run length = max(S min, 5 min). Timeout = max(10S, 300 s). Pause = timeout + 90 s.
- S is a measurement, not a setting: do not pick it. It depends on the laptop (GPU vs CPU, memory, power, other programs). The ~33 s in our notes is only an A1 estimate.
- For a fair S: plugged in, high-performance power plan, other apps closed, CPU only (`ollama ps` shows size_vram = 0, as the scripts require).
- With S about 33 s: rate about 55 per hour, window about 33 min, about 30 tickets per run, timeout 330 s, pause 420 s.

## 3. The 9 runs
| Config | What answers the ticket | Runs |
|---|---|---|
| `gemmaAlone` | gemma4:e4b only, thinking on (the A1 reference) | 3 |
| `cascadeS1` | phi3 first; gemma only when the S1 rule escalates | 3 |
| `cascadeS2` | phi3 first; gemma only when the S2 rule escalates | 3 |

Order is run-major: run 1 of all three configs, then run 2, then run 3.

If P3's accuracy results show another single model (e.g. mistral) passes both accuracy limits, add 3 runs for it. Likely not needed.

Each run takes roughly 40-50 min including setup. Total about 6 hours. Finished runs are skipped on restart, so you can split across sessions.

### Cascade S1 vs S2
phi3 (small, fast) guesses the category first. A rule accepts its answer or escalates to gemma (final answer).
- **S1 (cautious):** accepts phi3 for Consumer loan, Debt collection, Credit card, Money transfer or service. About 69% escalated. Slower, safer.
- **S2 (looser):** accepts those four plus Mortgage. About 46% escalated. Faster, more accuracy risk.
Escalation percentages are tuning-set estimates; the real fraction is measured from the server logs.

## 4. Steps for P1
1. `git pull` (P2 will have pushed `scripts/a2/`, `tests/load/speed_test.jmx`, `datasets/a2/speed/`).
2. Record your hardware (GPU, VRAM, RAM, Ollama version, settings) in the style of `loadgen_environment.md` (see `tests/environment/`).
3. Start Docker and Ollama. Both models must stay resident (memcheck passed earlier with about 3.5 GiB spare).
4. Open the firewall once (admin PowerShell):
   ```
   New-NetFirewallRule -DisplayName 'A2 control' -Direction Inbound -Protocol TCP -LocalPort 8099 -Action Allow -Profile Any
   ```
5. Measure S and derive parameters, then commit `datasets/a2/speed/`:
   ```
   powershell -ExecutionPolicy Bypass -File scripts\a2\setup_speed.ps1
   ```
6. Do one short trial first. These scripts have only been syntax-checked, never run against the real SUT. Fix problems before the real matrix.
7. Commit everything (the scripts refuse a dirty git tree outside `runs/`).
8. Run the matrix (it prints your IP; tell P2 the control URL `http://<your-IP>:8099`):
   ```
   powershell -ExecutionPolicy Bypass -File scripts\a2\p1_run_all.ps1 -Configs gemmaAlone,cascadeS1,cascadeS2
   ```
   (The script default is now these same 3 configs; passing `-Configs` is optional.)
9. When it prints ALL RUNS COMPLETE, commit `runs\`.

## 5. Steps for P2
1. Push the scripts and workload files.
2. Check JMeter at `C:\Users\natli\tools\apache-jmeter-5.6.3\bin\jmeter.bat`.
3. Once P1's SUT is up, re-record the load-generator environment (last record said "TCP connect to SUT: False").
4. During the matrix, leave this running until FINISHED:
   ```
   powershell -ExecutionPolicy Bypass -File scripts\a2\p2_run_loop.ps1 -ControlUrl http://<P1-IP>:8099
   ```
5. Commit `runs\` (.jtl files).

## 6. What happens inside every run
1. P1 switches config, restarts Ollama, rebuilds the server, checks `/health`.
2. P1 warms up with 3 fixed tickets and checks `ollama ps`.
3. P1 signals READY; P2's JMeter sends tickets for the window at the fixed rate (POST /tickets only).
4. When all requests finish, JMeter stops early (no waiting out the drain pause).
5. P2 reports DONE; P1 archives logs and `/stats`; `run_summary.py` writes `sut_summary.json`.
Run folders: `runs\<model>_speed_<Config>_run<N>`.

## 7. Accuracy runs (P3's results decide any extra single model)
```
powershell -ExecutionPolicy Bypass -File scripts\a2\accuracy_run.ps1 -Config gemmaAlone -Run 1
```
A single model needs speed tests only if it passes both limits (overall >= 61/88 and every per-category limit).

## 8. Rules to keep
- Same laptop for S and all runs. Both laptops on the same network, SUT plugged in.
- Never overwrite a run folder or edit evidence.
- Do not shorten the window without lecturer approval (`-DurationMinutes 5` is a declared deviation: slides 3 and 8).
- Speed runs use POST /tickets only, one fixed rate, open-model JMeter.
- Ignore the thinking-off material (`*NoThink` configs, `A2PredictionAddendum_thinking.md`); we are not doing it.

## 9. Open items before official runs
- [ ] Scripts committed and pulled by P1
- [ ] P1 hardware recorded
- [ ] Trial run passed
- [ ] S measured and `datasets/a2/speed/` committed
- [ ] Load-generator environment re-recorded with SUT reachable

Deadline: 2359, 27 Nov.
