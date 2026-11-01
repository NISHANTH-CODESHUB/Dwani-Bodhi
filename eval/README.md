# Evaluation (guide §14)

| Script | Dataset | Measures |
|---|---|---|
| `run_reading_eval.py --manifest …` | D-R1 planted-error recordings, D-R2 consented children | word accuracy, abstention, error-type macro-F1, ECE, accuracy by group, ECCL vs free-ASR ablation; `--fit` writes calibration |
| `run_slate_eval.py --labels …` | D-S1 planted-bug slates, D-S2 real slates | marker detection, answer exact-match, abstention, bug precision/recall; `--model` compares Sonnet vs Haiku |
| `smoke_speech_model.py` | — | model loads, vocabulary coverage, silence handling, CPU real-time factor |

`--simulate` / `--synthetic` modes only exercise the pipeline with synthetic inputs. **Never report them as accuracy.**

## Dataset layout (git-ignored: `eval/datasets/`)

```
eval/datasets/dr1/manifest.csv      clip,target,label_status,label_rule,group
eval/datasets/dr1/clips/*.webm
eval/datasets/ds1/labels.json       [{"image","problems":[{a,b,op}],"slates":[{"marker","answers":[...]}]}]
eval/datasets/ds1/*.jpg
```

## D-R1 planted-error protocol
- 10 consenting adult or teen volunteers each read 40 words and 3 passages.
- A script tells them which words to misread and how (e.g. read पीला as पिला).
- About 25% of words carry a planted error, covering every ECCL rule.
- Record on the real kiosk with classroom noise at about 60 dB.
- The script itself is the label, so no annotation is needed.

## D-S1 planted-bug slates
- Write 200 problems on real slates: 50 correct, 150 with bugs or slips from `app/diagnosis/bugs.py`.
- Each slate has an ID card.
- Photograph under daylight, dim light, glare and flash, on 3 phones, with 4–5 slates per photo.

Report every metric with *n*. Report misses honestly, and compare against human–human agreement (Cohen's κ) on D-R2.
