import re
import sys
from collections import Counter
from pathlib import Path

FRAME = re.compile(r"^\s+([\w.$]+)\.([\w$<>]+)\(")
STEP = re.compile(r"org\.audiveris\.omr\.(?:[\w.]+\.)?(\w+Step)\.")


def samples(path: Path):
    stack, inside = [], False
    for line in path.open(errors="replace"):
        if line.startswith("jdk.ExecutionSample"):
            stack, inside = [], False
        elif "stackTrace = [" in line:
            inside = True
        elif inside and line.strip() == "]":
            inside = False
            yield stack
        elif inside and (match := FRAME.match(line)):
            stack.append(f"{match.group(1)}.{match.group(2)}")


def main():
    path = Path(sys.argv[1])
    total, self_time, inclusive, steps = 0, Counter(), Counter(), Counter()
    heads_inclusive, heads_total = Counter(), 0
    for stack in samples(path):
        total += 1
        if not stack:
            continue
        self_time[stack[0]] += 1
        for frame in set(stack):
            inclusive[frame] += 1
        step = next((m.group(1) for frame in stack if (m := STEP.search(frame))), "other")
        steps[step] += 1
        if step == "HeadsStep":
            heads_total += 1
            for frame in set(stack):
                heads_inclusive[frame] += 1
    print(f"{total} samples")
    print("\nby step (first *Step frame on the stack):")
    for name, count in steps.most_common(20):
        print(f"  {100 * count / total:5.1f}%  {name}")
    print("\nself time, top 25:")
    for name, count in self_time.most_common(25):
        print(f"  {100 * count / total:5.1f}%  {name}")
    print(f"\ninside HeadsStep ({heads_total} samples), inclusive, top 25 Audiveris frames:")
    for name, count in [item for item in heads_inclusive.most_common(80) if "audiveris" in item[0]][:25]:
        print(f"  {100 * count / max(heads_total, 1):5.1f}%  {name}")


if __name__ == "__main__":
    main()
