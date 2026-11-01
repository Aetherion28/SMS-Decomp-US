#!/usr/bin/env python3
"""Build a playable DOL from this repository's own source code.

The normal build links our object only for units marked Matching and uses
the original (split) objects for everything else, so its DOL is the retail
one, byte for byte.
This script instead configures an "all source" build, where every unit,
Matching or not, is compiled from src/ and linked, and writes
<build-dir>/<version>/playable/mario.dol.

The original game was linked from static libraries (Enemy.a, NPC.a, ...),
and a few header-defined globals ended up in several objects; the map lists
the extra copies as "UNREFERENCED DUPLICATE".
Linking loose objects turns those into "multiply-defined" errors, so after a
failed link this script makes weak copies of the extra definitions (keeping
the one the map says was used) and links again.
The compiled objects themselves are left untouched, so ninja doesn't rebuild
them; the weakened copies live in playable/objs/.

The repository's own build.ninja and objdiff.json are regenerated for the
normal build when the script finishes.

A few units have little or no source yet (their objects are empty or much
smaller than the original), and the game needs them: the scene files place
those objects, and the object factories can't create classes we don't have.
For those units, and for any other whose compiled .text is more than
--fallback-bytes smaller than the original, the original object split from
the retail DOL is linked instead; the script lists them.
--pure turns this off and links only our source.

--oracle builds the ghost oracle (see tools/playable/oracle.cpp): every
object is compiled with -DSMS_ORACLE, which turns on the replay/logging hooks
in the sources, and oracle.cpp is linked in.

Usage: python3 tools/build_playable.py [--build-dir build_play]
       [--version GMSJ01] [--fallback-bytes 512] [--pure] [--oracle]
"""

import argparse
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, **kw)


def map_owners(map_path: Path):
    """symbol -> source file stem holding the copy the original linker used."""
    owners = {}
    pat = re.compile(
        r"\]\s+(\S+) \((?:object|func),\w+\) found in \S+ (\S+?)\.c(?:pp)?\s*$"
    )
    with open(map_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        m = pat.search(line)
        if m and i + 1 < len(lines) and "UNREFERENCED DUPLICATE" in lines[i + 1]:
            owners[m.group(1)] = m.group(2)
    return owners


def text_size(path: Path) -> int:
    out = run([str(ROOT / "build/binutils/powerpc-eabi-size"), "-A", str(path)]).stdout
    return sum(int(l.split()[1]) for l in out.splitlines() if l.startswith(".text"))


def use_original_where_missing(objects, ver_dir: Path, args):
    """Swap in the original object for units whose code is still missing."""
    src_dir = ver_dir / "src"
    result = []
    for obj in objects:
        path = ROOT / obj
        orig = ver_dir / "obj" / path.relative_to(src_dir) if path.is_relative_to(src_dir) else None
        if orig is not None and orig.exists():
            ours, theirs = text_size(path), text_size(orig)
            if theirs - ours > args.fallback_bytes:
                print(f"using the original object for {orig.relative_to(ver_dir / 'obj')} "
                      f"(our .text is 0x{ours:X} bytes, the original 0x{theirs:X})")
                result.append(str(orig.relative_to(ROOT)))
                continue
        result.append(obj)
    return result


def compile_extra(out_dir: Path, ver_rel: str, name: str):
    """Compile tools/playable/<name>.cpp with the game-code compiler flags."""
    cmd = ninja_command(f"{ver_rel}/src/Enemy/Koopa.o")
    if "&&" in cmd:
        cmd = cmd[: cmd.index("&&")]
    cmd = [a for a in cmd if a != "-MMD"]
    i = cmd.index("-c")
    glue_dir = (out_dir / "glue").relative_to(ROOT)
    (ROOT / glue_dir).mkdir(parents=True, exist_ok=True)
    cmd[i + 1] = f"tools/playable/{name}.cpp"
    cmd[cmd.index("-o") + 1] = str(glue_dir)
    r = run(cmd)
    obj = glue_dir / f"{name}.o"
    if r.returncode or not (ROOT / obj).exists():
        print(r.stdout, r.stderr)
        print(f"couldn't compile tools/playable/{name}.cpp")
        return None
    return obj.as_posix()


def map_path(version: str) -> Path:
    """The linker map named by config/<version>/config.yml."""
    cfg = (ROOT / "config" / version / "config.yml").read_text()
    m = re.search(r"^#?\s*map:\s*(\S+)", cfg, re.M)
    return ROOT / (m.group(1) if m else f"orig/{version}/files/mario.MAP")


def ninja_command(target: str) -> list:
    r = run(["ninja", "-t", "commands", target])
    return shlex.split(r.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default="build_play")
    ap.add_argument("--version", default="GMSJ01")
    ap.add_argument("--fallback-bytes", type=int, default=512)
    ap.add_argument("--pure", action="store_true")
    ap.add_argument("--oracle", action="store_true",
                    help="ghost oracle build: -DSMS_ORACLE and tools/playable/oracle.cpp")
    args = ap.parse_args()

    ver_dir = ROOT / args.build_dir / args.version
    out_dir = ver_dir / "playable"
    objcopy = ROOT / "build/binutils/powerpc-eabi-objcopy"
    owners = map_owners(map_path(args.version))

    cfg = [sys.executable, "configure.py", "--version", args.version,
           "--non-matching", "--all-source", "--build-dir", args.build_dir]
    if args.oracle:
        cfg += ["--define", "SMS_ORACLE"]
    r = run(cfg)
    if r.returncode:
        print(r.stdout, r.stderr)
        return 1

    try:
        elf_target = f"{args.build_dir}/{args.version}/mario.elf"
        dol_target = f"{args.build_dir}/{args.version}/mario.dol"
        link_cmd = ninja_command(elf_target)
        dol_cmd = ninja_command(dol_target)

        # compile everything; the link itself is done below
        r = run(["ninja", "-k", "0", elf_target])
        failed = [t for t in re.findall(r"^FAILED: (\S+)", r.stdout, re.M)
                  if t != elf_target]
        if failed:
            print(r.stdout[-6000:])
            print("these failed to build:", " ".join(failed))
            return 1

        out_dir.mkdir(parents=True, exist_ok=True)
        glue = compile_extra(out_dir, f"{args.build_dir}/{args.version}", "glue")
        if glue is None:
            return 1
        extra = []
        if args.oracle:
            oracle = compile_extra(out_dir, f"{args.build_dir}/{args.version}", "oracle")
            if oracle is None:
                return 1
            extra.append(oracle)
        rsp_arg = next(a for a in link_cmd if a.startswith("@"))
        objects = (ROOT / rsp_arg[1:]).read_text().split()
        if not args.pure:
            objects = use_original_where_missing(objects, ver_dir, args)
            objects.append(glue)
        objects += extra
        elf = out_dir / "mario.elf"
        dol = out_dir / "mario.dol"
        rsp = out_dir / "mario.elf.rsp"
        cmd = [str(elf.relative_to(ROOT)) if a == elf_target
               else "@" + str(rsp.relative_to(ROOT)) if a == rsp_arg
               else a for a in link_cmd]

        weak_copies = {}  # object path -> weakened copy
        for _ in range(10):
            rsp.write_text("\n".join(weak_copies.get(o, o) for o in objects) + "\n")
            r = run(cmd)
            out = r.stdout + r.stderr
            if r.returncode == 0:
                break
            dups = re.findall(
                r"multiply-defined: '([^']+)' in (\S+)\s*\n#\s+Previously defined in (\S+)",
                out)
            if not dups:
                print(out[-6000:])
                print("link failed for a reason other than duplicate symbols")
                return 1
            changed = False
            for sym, obj_a, obj_b in dups:
                owner = owners.get(sym)
                for name in (obj_a, obj_b):
                    if (Path(name).stem == owner) if owner else (name == dups[0][2]):
                        continue
                    matches = [o for o in objects if Path(o).name == name]
                    if len(matches) != 1:
                        print(f"can't find a unique {name} for {sym}: {matches}")
                        return 1
                    obj = matches[0]
                    copy = weak_copies.get(obj)
                    if copy is None:
                        copy = (out_dir / "objs" / Path(obj).relative_to(
                            f"{args.build_dir}/{args.version}")).relative_to(ROOT).as_posix()
                        (ROOT / copy).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(ROOT / obj, ROOT / copy)
                        weak_copies[obj] = copy
                    before = run([str(ROOT / "build/binutils/powerpc-eabi-nm"), copy]).stdout
                    if re.search(rf" [VW] {re.escape(sym)}$", before, re.M):
                        continue
                    run([str(objcopy), f"--weaken-symbol={sym}", copy])
                    changed = True
                    print(f"weakened {sym} in {name} "
                          f"(kept the copy in {owner or dups[0][2]})")
            if not changed:
                print(out[-6000:])
                print("duplicate symbols left that this script can't resolve")
                return 1
        else:
            print("gave up after 10 link attempts")
            return 1

        cmd = [str(elf.relative_to(ROOT)) if a.endswith("mario.elf")
               else str(dol.relative_to(ROOT)) if a.endswith("mario.dol")
               else a for a in dol_cmd]
        r = run(cmd)
        if r.returncode or not dol.exists():
            print(r.stdout[-4000:], r.stderr[-4000:])
            return 1
        print(f"wrote {dol.relative_to(ROOT)} ({dol.stat().st_size} bytes)")
        return 0
    finally:
        # restore the normal (matching) build files
        run([sys.executable, "configure.py", "--version", args.version])


if __name__ == "__main__":
    sys.exit(main())
