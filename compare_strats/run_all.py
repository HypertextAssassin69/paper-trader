import subprocess
import os
import sys

scripts = [
    "paper_trader.py",
    "paper_trader_strat_bullet_proof.py",
    "paper_trader_strat_v3_ml.py",
    "paper_trader_strat_v4_heuristic.py",
    "paper_trader_strat_ensemble_70_30.py",
    "paper_trader_strat_pairs.py",
    "paper_trader_strat_v7_large.py",
    "paper_trader_strat_v7_mid.py",
    "paper_trader_strat_v7_hybrid.py",
    "paper_trader_strat_v7_hybrid_50k.py",
    "paper_trader_strat_v7_cheap_20k.py"
]

def main():
    print("Starting master execution for all 11 paper trader strategies...")
    python_exe = sys.executable
    
    for s in scripts:
        if not os.path.exists(s):
            print(f"[ERROR] Script {s} does not exist in current directory.")
            continue
            
        print(f"\n--- Executing {s} ---")
        res = subprocess.run([python_exe, s], capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[ERROR] failed to run {s}:")
            print(res.stderr)
        else:
            print(f"[OK] Completed {s}. Output:")
            print(res.stdout.strip())

if __name__ == "__main__":
    main()
