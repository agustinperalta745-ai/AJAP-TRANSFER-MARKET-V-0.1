# AJAP PES6 PaddleOCR experiment

This branch is deliberately isolated from `main`.

## Goal

Prove whether a free local PaddleOCR reader can reliably extract AJAP PES6 result screenshots before any production integration.

The experiment does **not** import into the Discord bot, write the league database, change standings, or load results.

## Why this approach

Instead of OCR over the entire phone screenshot, `tools/pes6_paddle_probe.py`:

1. normalizes the phone/letterbox image;
2. crops known PES6 regions;
3. reads home team, away team and both large score digits separately;
4. reads the final-result/menu region;
5. exposes scorer-table text separately for later roster matching;
6. returns JSON only.

## Linux CPU setup

```bash
python -m pip install paddlepaddle==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
python -m pip install -r requirements-paddle-experiment.txt
```

Then run:

```bash
python tools/pes6_paddle_probe.py capture.png
```

Exit code `0` means both team regions, both score digits and a final-state marker were all read. Exit code `2` means the capture needs review; it must never invent missing values.

## Acceptance test before production

Do not merge this branch just because one screenshot succeeds. Test a representative batch of real AJAP images: different users, phone screenshots, result screens, scorer screens, licensed and unlicensed PES6 team names.

Suggested production gate:

- score: 100% correct in the test batch;
- team identity: 100% correct or explicitly unknown (never a wrong team);
- final/partial match state: no halftime capture accepted as final;
- scorers: only roster-matched names, with total attributed goals never exceeding the official score;
- runtime: comfortably below the Discord timeout on Railway CPU.

Only after those checks should the reader be wired into the live bot.
