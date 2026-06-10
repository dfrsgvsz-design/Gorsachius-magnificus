"""Check training progress — reads progress.json + history files."""
import json
from pathlib import Path

p = Path(__file__).parent.parent / "backend" / "checkpoints"

# Real-time progress
pp = p / "progress.json"
if pp.exists():
    prog = json.load(open(pp))
    s = prog.get("status", "?")
    phase = prog.get("phase", "?")
    ep = prog.get("epoch", 0)
    total_ep = prog.get("total_epochs", "?")
    pts = prog.get("total_data_points", 0)
    va = prog.get("val_acc", 0)
    t5 = prog.get("val_top5", 0)
    bva = prog.get("best_val_acc", 0)
    bt5 = prog.get("best_top5", 0)
    pat = prog.get("patience_counter", 0)
    mins = prog.get("elapsed_minutes", 0)
    ts = prog.get("timestamp", "?")

    print(f"{'='*60}")
    print(f" Phase: {phase.upper()}  Status: {s.upper()}")
    print(f"{'='*60}")
    if total_ep and total_ep != "?":
        print(f" Epoch:        {ep}/{total_ep} ({ep/total_ep*100:.0f}%)")
    else:
        print(f" Epoch:        {ep}")
    print(f" Data points:  {pts:,}")
    if va:
        print(f" Val accuracy: {va:.4f}  (best: {bva:.4f})")
        print(f" Val Top-5:    {t5:.4f}  (best: {bt5:.4f})")
    if pat:
        print(f" Patience:     {pat}/40")
    print(f" Elapsed:      {mins:.1f} min")
    print(f" Updated:      {ts}")
    print(f"{'='*60}")
else:
    print("No progress.json found — training may not have started yet.")

# Teacher history
th = p / "teacher_history.json"
if th.exists():
    h = json.load(open(th))
    va_list = h.get("val_acc", [])
    if va_list:
        last = va_list[-10:]
        print(f"\nTeacher: {len(va_list)} epochs, last 10: {[round(x,4) for x in last]}")
        print(f"  Best: {max(va_list):.4f} at ep{va_list.index(max(va_list))+1}")

# Student history
sh = p / "student_history.json"
if sh.exists():
    h = json.load(open(sh))
    va_list = h.get("val_acc", [])
    if va_list:
        last = va_list[-10:]
        print(f"\nStudent: {len(va_list)} epochs, last 10: {[round(x,4) for x in last]}")
        print(f"  Best: {max(va_list):.4f} at ep{va_list.index(max(va_list))+1}")

# V2 training history (fallback)
hp = p / "training_history.json"
if hp.exists() and not th.exists() and not sh.exists():
    h = json.load(open(hp))
    va_list = h.get("val_acc", [])
    if va_list:
        last = va_list[-10:]
        print(f"\nV2 History: {len(va_list)} epochs, last 10: {[round(x,4) for x in last]}")
        print(f"  Best: {max(va_list):.4f} at ep{va_list.index(max(va_list))+1}")

# Baselines
import torch
for name, fname in [("V1", "best_model_v1.pth"), ("V2", "best_model_v2.pth")]:
    fp = p / fname
    if fp.exists():
        c = torch.load(fp, map_location="cpu", weights_only=False)
        print(f"\n{name} baseline: val_acc={c.get('val_acc',0):.4f}, epoch={c.get('epoch','?')}")
