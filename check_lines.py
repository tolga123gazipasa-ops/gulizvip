import sys
filepath = "C:/Users/MSI/OneDrive/Desktop/gulizvip/index.html"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Print lines 904-993 with visible whitespace
for i in range(903, 993):
    if i < len(lines):
        print(f"{i+1}: {repr(lines[i])}", end="")
