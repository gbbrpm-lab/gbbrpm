from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model import load_network,evaluate_gbbrpm
for name in ["N1","N2","N3","N4","N5"]:
    n,e=load_network(ROOT/"data",name)
    r,_=evaluate_gbbrpm(n,e)
    assert all(0<=x<=1 for x in r.values())
print("Smoke test passed for N1-N5.")
