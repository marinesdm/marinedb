# coding: utf-8

import sys
import subprocess

jar_path = "gbif-date-parser.jar"


def parse_date(date_str, fmt=None):
    # Execute the java command with Popen and get the stdout from it
    cmd = ["java", "-jar", jar_path, date_str]
    if fmt is not None:
        cmd.append(fmt)

    a = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Process the stdout of the command
    stdout = []
    for line in a.stdout:
        line = line.decode("utf-8").strip()
        stdout.append(line.split(":")[1])

    if len(stdout) != 0:
        if len(stdout) != 1:
            sys.stderr.write("Error: More than one date found\n")
            sys.exit(-1)
        # Extract the two parsed dates
        stdout = stdout[0].split()
    else:
        stdout = ""

    stderr = []
    for line in a.stderr:
        line = line.decode("utf-8").strip()
        stderr.append(line.split(":")[1])

    if len(stderr) != 0:
        if len(stderr) != 1:
            sys.stderr.write("Error: More than one error found\n")
            sys.exit(-1)
        stderr = stderr[0]
    else:
        stderr = ""

    a.terminate()

    print(f"stdout: {stdout}, stderr : {stderr}")

    return stdout, stderr


if __name__ == "__main__":
    if len(sys.argv) not in [2, 3]:
        print("Usage: python parse.py <date> [format]")
        sys.exit(1)

    if len(sys.argv) == 3:
        parse_date(sys.argv[1], sys.argv[2])
    else:
        parse_date(sys.argv[1])
