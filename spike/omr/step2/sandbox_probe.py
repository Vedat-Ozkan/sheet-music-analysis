#!/usr/bin/env python3
import glob, json, os, platform, re, resource, shutil, subprocess, sys, tarfile, tempfile, time, urllib.request

VERSION = "5.11.0"
BASE = f"https://github.com/Audiveris/audiveris/releases/download/{VERSION}"
S = {"step": "start"}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def read(path):
    try:
        return open(path).read().strip()
    except OSError:
        return None


def machine():
    osr = dict(l.rstrip().split("=", 1) for l in (read("/etc/os-release") or "").splitlines() if "=" in l)
    mem = {k: int(v.split()[0]) // 1024 for k, v in (l.split(":", 1) for l in (read("/proc/meminfo") or "").splitlines())}
    work = tempfile.gettempdir()
    return {
        "python": platform.python_version(), "arch": platform.machine(),
        "os": osr.get("PRETTY_NAME", "").strip('"'), "os_version_id": osr.get("VERSION_ID", "").strip('"'),
        "cpus_visible": os.cpu_count(), "cpus_usable": len(os.sched_getaffinity(0)),
        "cgroup_cpu_max": read("/sys/fs/cgroup/cpu.max"), "cgroup_mem_max": read("/sys/fs/cgroup/memory.max"),
        "ram_total_mb": mem.get("MemTotal"), "ram_available_mb": mem.get("MemAvailable"),
        "disk_free_mb": shutil.disk_usage(work).free // 2**20, "workdir": work,
        "java": shutil.which("java"), "dpkg_deb": shutil.which("dpkg-deb"), "gnu_time": os.path.exists("/usr/bin/time"),
        "sudo": shutil.which("sudo"),
    }


def reach(url):
    t = time.time()
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "probe"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"ok": True, "status": r.status, "s": round(time.time() - t, 2)}
    except urllib.error.HTTPError as e:
        return {"ok": True, "status": e.code, "s": round(time.time() - t, 2)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:120]}


def unpack(deb, dest):
    if shutil.which("dpkg-deb"):
        r = sh(["dpkg-deb", "-x", deb, dest])
        if r.returncode:
            raise RuntimeError(r.stderr[:300])
        return "dpkg-deb"
    with open(deb, "rb") as f:
        assert f.read(8) == b"!<arch>\n"
        while True:
            h = f.read(60)
            if len(h) < 60:
                raise RuntimeError("no data.tar member")
            name, size = h[:16].decode().strip().rstrip("/"), int(h[48:58])
            if name.startswith("data.tar"):
                tmp = os.path.join(os.path.dirname(dest), name)
                with open(tmp, "wb") as o:
                    o.write(f.read(size))
                if name.endswith(".zst"):
                    sh([sys.executable, "-m", "pip", "install", "-q", "--user", "zstandard"])
                    import zstandard
                    with open(tmp, "rb") as i, open(tmp[:-4], "wb") as o:
                        zstandard.ZstdDecompressor().copy_stream(i, o)
                    tmp = tmp[:-4]
                with tarfile.open(tmp) as t:
                    try:
                        t.extractall(dest, filter="fully_trusted")
                    except TypeError:
                        t.extractall(dest)
                return "python-tarfile"
            f.seek(size + size % 2, 1)


def timed(cmd, env=None):
    t = time.time()
    if os.path.exists("/usr/bin/time"):
        r = sh(["/usr/bin/time", "-v"] + cmd, env=env)
        m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", r.stderr)
        rss, how = (int(m.group(1)) // 1024 if m else None), "/usr/bin/time -v"
    else:
        r = sh(cmd, env=env)
        rss, how = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024, "getrusage(children), covers all children so far"
    return r.returncode, round(time.time() - t, 1), rss, how, r.stderr[-400:]


def main():
    pdf = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    S["machine"] = machine()
    S["reach"] = {h: reach(u) for h, u in {
        "github.com": "https://github.com", "objects.githubusercontent.com": "https://objects.githubusercontent.com",
        "pypi.org": "https://pypi.org/simple/", "mcp.sheetmusicanalysis.com": "https://mcp.sheetmusicanalysis.com/",
        "sheetmusicanalysis.com": "https://sheetmusicanalysis.com/"}.items()}
    print(json.dumps(S, indent=1), flush=True)
    work = tempfile.mkdtemp(prefix="aud_")
    ubuntu = "ubuntu24.04" if S["machine"]["os_version_id"] == "24.04" else "ubuntu22.04"
    url = f"{BASE}/Audiveris-{VERSION}-{ubuntu}-x86_64.deb"
    deb = os.path.join(work, "a.deb")
    S["step"] = "download"
    t = time.time()
    urllib.request.urlretrieve(url, deb)
    S["download"] = {"url": url, "mb": round(os.path.getsize(deb) / 2**20, 1), "s": round(time.time() - t, 1)}
    S["step"] = "unpack"
    dest = os.path.join(work, "x")
    os.makedirs(dest)
    t = time.time()
    S["unpack"] = {"method": unpack(deb, dest), "s": round(time.time() - t, 1)}
    S["unpack"]["mb"] = int(sh(["du", "-sm", dest]).stdout.split()[0])
    exe = glob.glob(dest + "/opt/audiveris/bin/Audiveris")[0]
    env = dict(os.environ, HOME=work)
    S["step"] = "run"
    if pdf:
        out = os.path.join(work, "out")
        rc, s, rss, how, err = timed([exe, "-batch", "-export", "-output", out, pdf], env)
        S["run"] = {"pdf": os.path.basename(pdf), "returncode": rc, "s": s, "peak_ram_mb": rss, "peak_from": how,
                    "mxl": [os.path.basename(f) for f in glob.glob(out + "/**/*.mxl", recursive=True)]}
        if rc:
            S["run"]["stderr_tail"] = err
            omr = glob.glob(out + "/**/*.omr", recursive=True)
            if omr:
                rc2, s2, rss2, _, _ = timed([exe, "-batch", "-export", "-output", out, omr[0]], env)
                S["run"].update(reexport_returncode=rc2, reexport_s=s2,
                                mxl=[os.path.basename(f) for f in glob.glob(out + "/**/*.mxl", recursive=True)])
    else:
        S["run"] = "no PDF given"
    S["step"] = "done"
    shutil.rmtree(work, ignore_errors=True)


try:
    main()
except Exception as e:
    S["error"] = f"{type(e).__name__}: {e}"[:400]
print("SUMMARY " + json.dumps(S))
