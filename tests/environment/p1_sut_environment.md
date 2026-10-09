# P1 Official SUT - Test Environment Record

Generated 2026-09-26T13:41:17Z by `scripts/p1/record_environment.ps1` on the official SUT laptop. Values are read from the machine, Docker and Ollama APIs; nothing is typed in by hand.

## SUT machine (runs the triage service, MySQL and Ollama)

| Item | Value |
| --- | --- |
| Manufacturer / model | LENOVO 83DF |
| CPU | Intel(R) Core(TM) i9-14900HX - 24 cores / 32 threads, base 2200 MHz |
| RAM (host) | 31.7 GB |
| GPU(s) present | Intel(R) UHD Graphics; NVIDIA GeForce RTX 4060 Laptop GPU - NOT used: no GPU is passed into the Ollama container |
| OS | Microsoft Windows 11 Home 10.0.26200 (build 26200) |
| Power at record time | AC=True, battery 99%, Windows power mode 'Balanced' |
| Power scheme | Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) |
| Docker | Docker Desktop 4.72.0 (225998) / engine 29.4.2 |
| Docker Compose | 5.1.3 |
| Docker VM (WSL2) resources | 32 vCPU, 16619610112 bytes RAM, kernel 6.18.33.2-microsoft-standard-WSL2 |
| WSL | WSL version: 2.7.14.0; Kernel version: 6.18.33.2-2 |

## Service stack (docker compose, project `ict3113-p2-2`)

| Service | Image (tag + digest) | Image ID |
| --- | --- | --- |
| mysql | ["mysql:8.0","mysql:8.0.46"] ["mysql@sha256:7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b"] | 7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b |
| ollama | ["ollama/ollama:0.34.4","ollama/ollama:latest"] ["ollama/ollama@sha256:8262851b2846b87c649eddf3e76beb270c52f4d1bc94559f47efde16b0841551"] | 8262851b2846b87c649eddf3e76beb270c52f4d1bc94559f47efde16b0841551 |
| server | ["ict3113-p2-2-server:latest"] ["ict3113-p2-2-server@sha256:d7a1fb9d74592ab03501c6474719def2c6fb163ce367f1125dfc134753e9c039"] | d7a1fb9d74592ab03501c6474719def2c6fb163ce367f1125dfc134753e9c039 |

| Setting | Value |
| --- | --- |
| Ollama version | 0.34.4 |
| Inference compute (Ollama startup log) | msg="inference compute" id=cpu library=cpu compute="" name=cpu description=cpu libdirs=ollama driver="" pci_id="" type="" total="15.5 GiB" available="15.4 GiB" |
| OLLAMA_NUM_PARALLEL | 1 |
| OLLAMA_MAX_LOADED_MODELS | 1 |
| OLLAMA_MAX_QUEUE | 512 |
| OLLAMA_KEEP_ALIVE | 2562047h47m16.854775807s |
| OLLAMA_CONTEXT_LENGTH (0 = default, 4096 on CPU) | 0 |
| OLLAMA_FLASH_ATTENTION | false |
| Service model / prompt / think | model=gemma4:e4b, prompt=v1, think=default |
| Classifier call | POST /api/generate, stream=false, temperature=0, seed=42, JSON-schema format (7-category enum), timeout 600 s |

## Candidate models (Docker Ollama store)

| Tag | Full digest | Short ID | Step 4 ID | Size | Params | Quant |
| --- | --- | --- | --- | --- | --- | --- |
| llama3.2:1b | baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878 | baf6a787fdff | baf6a787fdff (match) | 1.23 GB | 1.2B | Q8_0 |
| phi3:3.8b | 4f222292793889a9a40a020799cfd28d53f3e01af25d48e06c5e708610fc47e9 | 4f2222927938 | 4f2222927938 (match) | 2.03 GB | 3.8B | Q4_0 |
| mistral:7b | 6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf | 6577803aa9a0 | 6577803aa9a0 (match) | 4.07 GB | 7.2B | Q4_K_M |
| gemma4:e4b | c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb | c6eb396dbd59 | c6eb396dbd59 (match) | 8.95 GB | 8.0B | Q4_K_M |

## CPU-only evidence

- Ollama found no GPU at startup: `msg="inference compute" id=cpu library=cpu compute="" name=cpu description=cpu libdirs=ollama driver="" pci_id="" type="" total="15.5 GiB" available="15.4 GiB"`
- `/api/ps`: gemma4:e4b resident, size=9426561924 bytes, **size_vram=0**

```
NAME          ID              SIZE      PROCESSOR    CONTEXT    UNTIL   
gemma4:e4b    c6eb396dbd59    9.4 GB    100% CPU     4096       Forever    
```

## Network

| Item | Value |
| --- | --- |
| Adapter | Wi-Fi - Intel(R) Wi-Fi 6E AX211 160MHz, 195 Mbps |
| Wi-Fi SSID | Hello Kitty-5GHz |
| IPv4 / gateway | 192.168.0.104 / 192.168.0.1 |
| Windows network category | Hello Kitty-5GHz [Public] |
| Service URL for testers | http://192.168.0.104:8000 |
| Firewall rule for TCP 8000 | present, enabled=True, profile=Any |
| MySQL 3306 / Ollama 11434 | bound to 127.0.0.1 only - not reachable from the LAN |

## Code baseline

| Item | Value |
| --- | --- |
| Branch @ commit | p1/sut-infra @ 418c6125942df32b0e773da75d15a2e25417534d |
| Uncommitted changes (excl. runs/, docs/environment/) | none |
| Frozen: datasets/golden_test_set.csv | 0630ef5 2026-09-16 00:21:32 +0800 phoebe |
| Frozen: datasets/labelling_protocol_v3.md | 4ce4fa2 2026-09-15 23:35:12 +0800 Nicholas-Kai-Yuan |
| Frozen: datasets/PredictionRecord.pdf | 8dbec5d 2026-09-24 22:53:06 +0800 Moses Loh |

## Known limitations (for Slide 7)

- Consumer gaming laptop, not a server: hybrid P/E-core CPU whose boost clocks depend on temperature and power mode, so long runs can throttle.
- Inference runs inside Docker Desktop's WSL2 VM, which sees only part of the host RAM (see the Docker VM row); Windows and WSL add some overhead.
- Network is Wi-Fi unless noted otherwise: latency jitter between the load generator and the SUT is part of every measured response time.
- Docker Desktop port forwarding hides the tester's real IP (the service log shows the Docker gateway), so runs are told apart by time window and the optional X-Run-Id header.
- Background Windows activity (updates, antivirus scans) cannot be fully excluded; heavy apps are closed before official runs.
