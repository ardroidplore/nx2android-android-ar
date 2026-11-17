#!/usr/bin/env python3
"""Patches a nx2android checkout for an aarch64 phone. Idempotent; each patch reports ok / already / FAILED (upstream text changed)."""
import sys
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
failed = 0


def patch(name, rel, marker, edits, requires=None):
    """edits: a list of (old, new), or a list of such lists (alternatives for different upstream versions: the first one whose texts all fit is used).
    requires: text that must already be in the file (a patch this one builds on); without it this patch is not applied, so no half-patched file is left behind."""
    global failed
    f = repo / rel
    try: s = f.read_text()
    except OSError as e: print(f'{name}: FAILED (cannot read {rel}: {e})'); failed += 1; return
    if marker in s: print(f'{name}: already'); return
    if requires and requires not in s: print(f'{name}: FAILED (not applied: it needs the patch that adds {requires!r}, which did not fit)'); failed += 1; return
    alts = edits if edits and isinstance(edits[0], list) else [edits]
    for alt in alts:
        t = s
        if all(t.count(old) == 1 for old, _ in alt):
            for old, new in alt: t = t.replace(old, new)
            f.write_text(t); print(f'{name}: ok'); return
    old = next((o for o, _ in alts[-1] if s.count(o) != 1), '')
    print(f'{name}: FAILED (upstream changed: {old[:50]!r})'); failed += 1


# 1. the NDK's own tools are x86-64: use the system clang/glslc with the NDK sysroot, the system clang's headers and the NDK's runtime libraries
ARM_BLOCK = """import platform as _pf, shutil as _sh, stat as _st0
@@HOSTLINE@@
NX2A_ARM_HOST = @@COND@@sys.platform.startswith('linux') and _pf.machine().lower() in ('aarch64', 'arm64')
if NX2A_ARM_HOST:
    _sysroot = next(Path(a.ndk).glob('toolchains/llvm/prebuilt/*/sysroot'), None)
    _ndkres = next(iter(sorted(Path(a.ndk).glob('toolchains/llvm/prebuilt/*/lib/clang/*'))), None)
    _sys_clang = _sh.which('clang')
    if not (_sysroot and _ndkres and _sys_clang): sys.exit('aarch64 host: need the NDK download (its sysroot) and the system clang (apt install clang lld)')
    _sysres = Path(subprocess.check_output([_sys_clang, '-print-resource-dir'], text=True).strip())
    _wd = Path(a.out if a.out else DM / 'android/out'); _wd.mkdir(parents=True, exist_ok=True)
    _rd = _wd / 'resdir'; _rd.mkdir(exist_ok=True)
    for _n, _t in (('include', _sysres / 'include'), ('lib', _ndkres / 'lib')):
        _l = _rd / _n
        if _l.is_symlink() or _l.exists(): _l.unlink()
        _l.symlink_to(_t)
    _wrap = _wd / 'cc-arm'
    _wrap.write_text(f'#!/bin/sh\\nexec {_sys_clang} --sysroot={_sysroot} -resource-dir={_rd} -rtlib=compiler-rt "$@"\\n')
    _wrap.chmod(_wrap.stat().st_mode | _st0.S_IXUSR)
    CC = str(_wrap)
"""
STRIP_OLD = "subprocess.run([str(bin_ / ('llvm-strip.exe' if os.name == 'nt' else 'llvm-strip')), '--strip-unneeded', str(out / 'libdmhost.so')], check=True)"
STRIP_NEW = "subprocess.run([str(_sh.which('llvm-strip') or _sh.which('llvm-strip-18') or 'strip') if NX2A_ARM_HOST else str(bin_ / ('llvm-strip.exe' if os.name == 'nt' else 'llvm-strip')), '--strip-unneeded', str(out / 'libdmhost.so')], check=True)"
CC_LINE = "CC = str(bin_ / ('clang.exe' if os.name == 'nt' else 'clang'))\n"
patch('arm host build', 'nxnative/dm/android/build.py', 'NX2A_ARM_HOST', [
    # older upstream: the host folder chosen inline
    [("host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64' if sys.platform.startswith('linux') else 'darwin-x86_64'\nbin_ = Path(a.ndk) / 'toolchains/llvm/prebuilt' / host / 'bin'\n" + CC_LINE,
      ARM_BLOCK.replace('@@COND@@', '').replace('@@HOSTLINE@@', "host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64' if sys.platform.startswith('linux') else 'darwin-x86_64'\nbin_ = Path(a.ndk) / 'toolchains/llvm/prebuilt' / host / 'bin'\n" + CC_LINE)),
     ("GLSLC = Path(a.ndk) / 'shader-tools' / host / ('glslc.exe' if os.name == 'nt' else 'glslc')\n",
      "GLSLC = Path(a.ndk) / 'shader-tools' / host / ('glslc.exe' if os.name == 'nt' else 'glslc')\nif NX2A_ARM_HOST: GLSLC = Path(_sh.which('glslc') or sys.exit('aarch64 host: apt install glslc'))\n"),
     (STRIP_OLD, STRIP_NEW)],
    # newer upstream: host_dir() (an NDK folder linux-aarch64 is used by upstream itself when it holds the tool; this patch only steps in when it does not)
    [("host = host_dir('toolchains/llvm/prebuilt', 'bin/clang')\nbin_ = Path(a.ndk) / 'toolchains/llvm/prebuilt' / host / 'bin'\n" + CC_LINE,
      ARM_BLOCK.replace('@@COND@@', "host == 'linux-x86_64' and ").replace('@@HOSTLINE@@', "host = host_dir('toolchains/llvm/prebuilt', 'bin/clang')\nbin_ = Path(a.ndk) / 'toolchains/llvm/prebuilt' / host / 'bin'\n" + CC_LINE)),
     ("GLSLC = Path(a.ndk) / 'shader-tools' / host_dir('shader-tools', 'glslc') / ('glslc.exe' if os.name == 'nt' else 'glslc')\n",
      "GLSLC = Path(a.ndk) / 'shader-tools' / host_dir('shader-tools', 'glslc') / ('glslc.exe' if os.name == 'nt' else 'glslc')\nif NX2A_ARM_HOST: GLSLC = Path(_sh.which('glslc') or sys.exit('aarch64 host: apt install glslc'))\n"),
     (STRIP_OLD, STRIP_NEW)],
])

# 1b. the same wrapper for C++ (the custom-driver loader libadrenotools is C++): the trimmed NDK has no clang++, use the system one with the NDK sysroot
patch('arm host c++', 'nxnative/dm/android/build.py', 'cxx-arm', [
("""    CXX = str(bin_ / ('clang++.exe' if os.name == 'nt' else 'clang++'))
""", """    CXX = str(bin_ / ('clang++.exe' if os.name == 'nt' else 'clang++'))
    if NX2A_ARM_HOST:
        _sys_cxx = _sh.which('clang++') or (_sys_clang + '++')
        _wrx = _wd / 'cxx-arm'
        _wrx.write_text(f'#!/bin/sh\\nexec {_sys_cxx} --sysroot={_sysroot} -resource-dir={_rd} -rtlib=compiler-rt "$@"\\n')
        _wrx.chmod(_wrx.stat().st_mode | _st0.S_IXUSR)
        CXX = str(_wrx)
"""),
], requires='NX2A_ARM_HOST')

# 2. every port gets the package unknownnone.nx2android.<game name> unless --package is given
patch('package names', 'porter/pipeline.py', "'unknownnone.nx2android.'", [
('self.package = o.package or ap.package',
 "self.package = o.package or 'unknownnone.nx2android.' + (re.sub(r'^[^a-z]+|[^a-z0-9]', '', ap.name.lower()) or 'game')"),
])
# 3. prebuilt .NET tools (CI-built, a runtime that starts under proot): used when the app has installed and tested them (NX2A_PREBUILT)
patch('prebuilt extractor', 'nxnative/scripts/build_ipa_from_nsp.py', 'NX2A_PREBUILT', [
("""    nx = work / 'tools/nx_extract' / exe
""", """    nx = work / 'tools/nx_extract' / exe
    if os.environ.get('NX2A_PREBUILT') and (Path(os.environ['NX2A_PREBUILT']) / 'nx_extract' / 'nx_extract').is_file():   # NX2A_PREBUILT: the app's prebuilt tools
        rmtree(nx.parent); shutil.copytree(Path(os.environ['NX2A_PREBUILT']) / 'nx_extract', nx.parent); return nx
"""),
])
patch('prebuilt translator', 'porter/pipeline.py', 'NX2A_PREBUILT', [
("""        src = DM / 'gfx/tools/dmsh_xlate'; ryu = DM / 'third_party/ryujinx'
""", """        if os.environ.get('NX2A_PREBUILT') and (Path(os.environ['NX2A_PREBUILT']) / 'dmsh_xlate' / 'dmsh_xlate').is_file():   # NX2A_PREBUILT: the app's prebuilt tools
            return Path(os.environ['NX2A_PREBUILT']) / 'dmsh_xlate' / 'dmsh_xlate.dll', 'prebuilt'
        src = DM / 'gfx/tools/dmsh_xlate'; ryu = DM / 'third_party/ryujinx'
"""),
])
patch('prebuilt dotnet check', 'porter/toolchain.py', 'NX2A_PREBUILT', [
("""    cfg = cfg if cfg is not None else config.load()
    if cfg.get('dotnet') and Path(cfg['dotnet']).is_file(): return Path(cfg['dotnet'])
""", """    cfg = cfg if cfg is not None else config.load()
    if os.environ.get('NX2A_PREBUILT_DOTNET') and Path(os.environ['NX2A_PREBUILT_DOTNET']).is_file(): return Path(os.environ['NX2A_PREBUILT_DOTNET'])   # NX2A_PREBUILT
    if cfg.get('dotnet') and Path(cfg['dotnet']).is_file(): return Path(cfg['dotnet'])
"""),
("""def dotnet_sdks(dotnet):   # {'10.0.402': '/usr/local/share/dotnet/sdk', ...}
""", """def dotnet_sdks(dotnet):   # {'10.0.402': '/usr/local/share/dotnet/sdk', ...}
    if os.environ.get('NX2A_PREBUILT_DOTNET') and str(dotnet) == os.environ['NX2A_PREBUILT_DOTNET']: return {'10.0.0': '/nx2a-prebuilt/sdk'}   # stands in for the SDK: the tools are prebuilt
"""),
])
# 4. Screen scale: a "Screen" row in the pause menu (Game tab) that cycles Fit / Stretch / Zoom, so the picture can fill a wider screen than 16:9
# (gfx_vk_present.c present_window). All three files or none: if upstream's text changed in any of them the patch is skipped (the port works as before).
# env DM_SCALE_MODE=stretch|zoom (env.txt) sets the start value until the player chooses in the menu. Zoom: touch points are off by the cut edges.
SCREEN_SCALE = {
    'overlay_layout.h': [
        ('OVM_PAD, OVM_AUDIO, OVM_RESUME, OVM_TAB, OVM_N };',
         'OVM_PAD, OVM_AUDIO, OVM_SCALE, OVM_RESUME, OVM_TAB, OVM_N };'),
        ("// OVM_PAD: a controller's face buttons by their position or by their label (front_android.c pad_labels)",
         "// OVM_PAD: a controller's face buttons by their position or by their label (front_android.c pad_labels); OVM_SCALE: how the picture fills the window,\n            // fit | stretch | zoom (front_android.c dm_scale_mode, gfx_vk_present.c present_window)"),
        ('#define OVM_PER_TAB 5',
         '#define OVM_PER_TAB 6'),
        ('{{OVM_OVERLAY, OVM_OPACITY, OVM_EDIT, OVM_RUMBLE, OVM_PAD}, {OVM_FPS, OVM_MODE, OVM_EXPORT, OVM_IMPORT, OVM_AUDIO}};',
         '{{OVM_OVERLAY, OVM_OPACITY, OVM_EDIT, OVM_RUMBLE, OVM_PAD, -1}, {OVM_FPS, OVM_MODE, OVM_SCALE, OVM_EXPORT, OVM_IMPORT, OVM_AUDIO}};'),
    ],
    'gfx_vk_present.c': [
        ('__attribute__((weak)) int dm_overlay_visible(void) { return 0; }',
         '__attribute__((weak)) int dm_overlay_visible(void) { return 0; }\n__attribute__((weak)) int dm_scale_mode(void) { return 0; }   // front_android.c: how the picture fills the window: 0 fit (aspect kept, black borders), 1 stretch, 2 zoom (aspect kept, edges cut)'),
        ('"Face buttons", "Audio output", "Resume", ""};',
         '"Face buttons", "Audio output", "Screen", "Resume", ""};'),
        ('[OVM_AUDIO] = "Select"};',
         '[OVM_AUDIO] = "Select", [OVM_SCALE] = "Stretch"};   // (OVM_SCALE: the widest of OVM_SCALES, for the row\'s width; the button shows the current one)'),
        ('static const char *const OVM_PADS[2] = {"Position", "Label"};',
         'static const char *const OVM_SCALES[3] = {"Fit", "Stretch", "Zoom"};   // how the picture fills the window (front_android.c dm_scale_mode)\nstatic const char *const OVM_PADS[2] = {"Position", "Label"};'),
        ('        } else if (OVM_BUTTONS[it]) {   // a button\n',
         "        } else if (it == OVM_SCALE) {   // a button with the current mode's word, as wide as the widest, so that the row does not change its size\n            float bw = cv_text_w(OVM_BUTTONS[it], is) + 2 * sh, b[4] = {x1 - bw, cy - rh * 0.30f, bw, rh * 0.60f}; cv_button(cv, b, OVM_SCALES[(st >> 29 & 3) % 3], 0, 0);\n        } else if (OVM_BUTTONS[it]) {   // a button\n"),
        ('    double s = fmin((double)g_sext.width / cw, (double)g_sext.height / ch); int dw = (int)(cw * s), dh = (int)(ch * s), dx = ((int)g_sext.width - dw) / 2, dy = ((int)g_sext.height - dh) / 2;\n',
         "    // How the picture fills the window (front_android.c dm_scale_mode, the pause menu's Screen row; env DM_SCALE_MODE until the player chooses):\n    // fit: the aspect kept, black borders; stretch: the whole window, the aspect given up; zoom: the whole window, the aspect kept, the picture's edges cut\n    // (the source rectangle shrinks to the window's aspect: a blit's destination must lie inside the image, so the picture is not drawn larger than it)\n    int wsx = (int)g_sext.width, wsy = (int)g_sext.height, mode = dm_scale_mode(), dw, dh, dx, dy;\n    if (mode == 1) { dw = wsx; dh = wsy; dx = dy = 0; }\n    else if (mode == 2) {\n        double z = fmax((double)wsx / cw, (double)wsy / ch); int vw = (int)(wsx / z + 0.5), vh = (int)(wsy / z + 0.5);\n        if (vw > cw) vw = cw; if (vh > ch) vh = ch; if (vw < 1) vw = 1; if (vh < 1) vh = 1;\n        cx += (cw - vw) / 2; cy += (ch - vh) / 2; cw = vw; ch = vh; dw = wsx; dh = wsy; dx = dy = 0;\n    } else {\n        double s = fmin((double)wsx / cw, (double)wsy / ch); dw = (int)(cw * s); dh = (int)(ch * s); dx = (wsx - dw) / 2; dy = (wsy - dh) / 2;\n    }\n"),
    ],
    'front_android.c': [
        ("static _Atomic int g_set_grid;   // the layout editor's Snap to grid",
         'static _Atomic int g_set_grid;   // the layout editor\'s Snap to grid\nstatic _Atomic int g_set_scale = -1;   // how the picture fills the window: 0 fit, 1 stretch, 2 zoom (the menu\'s Screen row); -1: as env DM_SCALE_MODE says (fit, stretch, zoom)\nint dm_scale_mode(void) {   // gfx_vk_present.c present_window\n    int v = atomic_load(&g_set_scale); if (v >= 0) return v;\n    const char *e = getenv("DM_SCALE_MODE"); if (!e || !*e) return 0;\n    char c = e[0] | 0x20; return c == \'s\' || e[0] == \'1\' ? 1 : c == \'z\' || e[0] == \'2\' ? 2 : 0;\n}'),
        ('        else if (sscanf(line, "fps=%d", &v) == 1) atomic_store(&g_set_fps, v != 0);\n',
         '        else if (sscanf(line, "fps=%d", &v) == 1) atomic_store(&g_set_fps, v != 0);\n        else if (sscanf(line, "scale=%d", &v) == 1) atomic_store(&g_set_scale, v < 0 || v > 2 ? 0 : v);\n'),
        ('    if (atomic_load(&g_set_labels) >= 0) fprintf(f, "labels=%d\\n", atomic_load(&g_set_labels));',
         '    if (atomic_load(&g_set_scale) >= 0) fprintf(f, "scale=%d\\n", atomic_load(&g_set_scale));   // (only once the player chose: until then env DM_SCALE_MODE decides)\n    if (atomic_load(&g_set_labels) >= 0) fprintf(f, "labels=%d\\n", atomic_load(&g_set_labels));'),
        ('atomic_load(&g_sv_st) << 20 | (atomic_load(&g_sv_n) & 15) << 24 | pad_labels() << 28;',
         'atomic_load(&g_sv_st) << 20 | (atomic_load(&g_sv_n) & 15) << 24 | pad_labels() << 28 | (dm_scale_mode() & 3) << 29;'),
        ('    else if (item == OVM_PAD) { atomic_store(&g_set_labels, !pad_labels()); settings_save(); }',
         '    else if (item == OVM_SCALE) { atomic_store(&g_set_scale, (dm_scale_mode() + 1) % 3); settings_save(); dm_overlay_redraw(); }   // fit -> stretch -> zoom, shown at once (the held frame is drawn again)\n    else if (item == OVM_PAD) { atomic_store(&g_set_labels, !pad_labels()); settings_save(); }'),
    ],
}


def patch_group(name, marker, group):
    todo = {}
    for rel, edits in group.items():
        try: s = (repo / rel).read_text()
        except OSError as e: print(f'{name}: skipped (cannot read {rel}: {e})'); return
        if marker in s: continue   # this file has it already
        for old, new in edits:
            if s.count(old) != 1: print(f'{name}: skipped, not applied (upstream changed in {rel}: {old[:50]!r}); the port works without it'); return
            s = s.replace(old, new)
        todo[rel] = s
    if not todo: print(f'{name}: already'); return
    for rel, s in todo.items(): (repo / rel).write_text(s)
    print(f'{name}: ok')


patch_group('screen scale', 'dm_scale_mode', {'nxnative/dm/android/' + k: v for k, v in SCREEN_SCALE.items()})

sys.exit(1 if failed else 0)
