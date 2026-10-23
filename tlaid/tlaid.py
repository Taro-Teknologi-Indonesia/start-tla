#!/usr/bin/env python3
"""TLA-ID prototype.

  tlaid.py tla   FILE.tlaid|FILE.cfgid [OUTDIR]   Indonesian -> TLA+ (column preserving)
  tlaid.py impor FILE.tla|FILE.cfg     [OUTDIR]   TLA+ -> Indonesian (re-lays out columns)
  tlaid.py cek   Spec.tlaid [TLC args...]         transpile the folder, run TLC, translate output
  tlaid.py urai  Spec.tlaid                       transpile the folder, run SANY, translate output
  tlaid.py repl  [FILE]                           TLA-ID REPL (reads FILE instead of the keyboard if given)
  tlaid.py baru  Folder/Nama                      start a new spec: Nama.tlaid + Nama.cfgid
"""
import json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
JAR = os.environ.get("TLA_JAR") or os.path.join(HERE, "..", "tools", "tla2tools.jar")

# ---------------------------------------------------------------- keyword tables
# Indonesian keyword -> TLA+ token.  None = decided by context:
#   MAKA     -> THEN after JIKA, IN after MISALKAN, -> in a KASUS arm
#   TERHADAP -> the _ of ADIL_LEMAH/ADIL_KUAT TERHADAP v (A), i.e. WF_v(A) / SF_v(A)
#   ATAU STUTTERING -> the _ of [A]_v, written [A] ATAU STUTTERING v
#   DAN BERUBAH     -> the _ of <<A>>_v, written <<A>> DAN BERUBAH v
#   TETAP    -> UNCHANGED; written after its operand (x TETAP) it is moved in front
#   BERNILAI -> |-> directly inside [ ... ], :> anywhere else
#   KECUALI  -> EXCEPT; each change repeats the function in front of KECUALI:
#               [seen KECUALI seen[r] = 0, seen[q].n = LAMA + 1]  ->  [seen EXCEPT ![r] = 0, ![q].n = @ + 1]
SPEC_KW = {
    "MODUL": "MODULE", "MENGGUNAKAN": "EXTENDS", "KONSTANTA": "CONSTANTS",
    "VARIABEL": "VARIABLE", "ASUMSI": "ASSUME", "TEOREMA": "THEOREM",
    "INSTANSIASI": "INSTANCE", "DENGAN": "WITH", "LOKAL": "LOCAL", "REKURSIF": "RECURSIVE",
    "DAN": "/\\", "ATAU": "\\/", "TIDAK": "~", "BERARTI": "=>", "SETARA": "<=>",
    "BENAR": "TRUE", "SALAH": "FALSE",
    "SEMUA": "\\A", "ADA": "\\E", "PILIH": "CHOOSE",
    "BERLAKU": ":", "SEHINGGA": ":", "UNTUK": ":",
    "BERNILAI": None, "SERTA": "@@", "KE": "->", "STUTTERING": None, "BERUBAH": None,
    "TERHADAP": None, "ADIL_LEMAH": "WF", "ADIL_KUAT": "SF", "LAMA": "@",
    "DALAM": "\\in", "GABUNGAN": "\\cup", "IRISAN": "\\cap", "SELISIH": "\\",
    "HIMPUNAN_KUASA": "SUBSET", "GABUNGAN_SEMUA": "UNION", "SILANG": "\\X",
    "KECUALI": "EXCEPT",
    "JIKA": "IF", "MAKA": None, "SEBALIKNYA": "ELSE",
    "KASUS": "CASE", "LAINNYA": "OTHER", "MISALKAN": "LET",
    "TETAP": "UNCHANGED", "MUNGKIN": "ENABLED",
    "SELALU": "[]", "AKHIRNYA": "<>", "MENUJU": "~>",
    "BAGI": "\\div", "SAMBUNG": "\\o",
}
PHRASES = {("TIDAK", "DALAM"): "\\notin", ("BAGIAN", "DARI"): "\\subseteq", ("UNTUK", "SEMUA"): "\\A"}
FAIR = {"ADIL_LEMAH_": "WF_", "ADIL_KUAT_": "SF_"}
BULLETS_ID = {"DAN", "ATAU"}
BULLETS_TLA = {"/\\", "\\/", "\\land", "\\lor"}

CFG_KW = {
    "SPESIFIKASI": "SPECIFICATION", "AWAL": "INIT", "LANJUT": "NEXT",
    "INVARIAN": "INVARIANT", "PROPERTI": "PROPERTY", "KONSTANTA": "CONSTANTS",
    "BATASAN": "CONSTRAINT", "BATASAN_AKSI": "ACTION_CONSTRAINT", "SIMETRI": "SYMMETRY",
    "TAMPILAN": "VIEW", "CEK_KEBUNTUAN": "CHECK_DEADLOCK",
}
CFG_VALUES = {"BENAR": "TRUE", "SALAH": "FALSE"}

# TLA+ -> Indonesian, for `impor`
REV_WORD = {
    "MODULE": "MODUL", "EXTENDS": "MENGGUNAKAN", "CONSTANT": "KONSTANTA", "CONSTANTS": "KONSTANTA",
    "VARIABLE": "VARIABEL", "VARIABLES": "VARIABEL", "ASSUME": "ASUMSI", "THEOREM": "TEOREMA",
    "INSTANCE": "INSTANSIASI", "WITH": "DENGAN", "LOCAL": "LOKAL", "RECURSIVE": "REKURSIF",
    "TRUE": "BENAR", "FALSE": "SALAH", "CHOOSE": "PILIH", "SUBSET": "HIMPUNAN_KUASA",
    "UNION": "GABUNGAN_SEMUA", "EXCEPT": "KECUALI", "IF": "JIKA", "THEN": "MAKA",
    "ELSE": "SEBALIKNYA", "CASE": "KASUS", "OTHER": "LAINNYA", "LET": "MISALKAN", "IN": "MAKA",
    "UNCHANGED": "TETAP", "ENABLED": "MUNGKIN",
}
REV_SYM = {
    "/\\": "DAN", "\\land": "DAN", "\\/": "ATAU", "\\lor": "ATAU", "~": "TIDAK", "\\lnot": "TIDAK",
    "\\neg": "TIDAK", "=>": "BERARTI", "<=>": "SETARA", "\\equiv": "SETARA", "\\A": "SEMUA",
    "\\E": "ADA", "\\in": "DALAM", "\\notin": "TIDAK DALAM", "\\subseteq": "BAGIAN DARI",
    "\\cup": "GABUNGAN", "\\union": "GABUNGAN", "\\cap": "IRISAN", "\\intersect": "IRISAN",
    "\\": "SELISIH", "\\X": "SILANG", "\\times": "SILANG", "[]": "SELALU", "<>": "AKHIRNYA",
    "~>": "MENUJU", "\\div": "BAGI", "\\o": "SAMBUNG", "\\circ": "SAMBUNG",
}
REV_CFG = {
    "SPECIFICATION": "SPESIFIKASI", "INIT": "AWAL", "NEXT": "LANJUT", "INVARIANT": "INVARIAN",
    "INVARIANTS": "INVARIAN", "PROPERTY": "PROPERTI", "PROPERTIES": "PROPERTI",
    "CONSTANT": "KONSTANTA", "CONSTANTS": "KONSTANTA", "CONSTRAINT": "BATASAN",
    "CONSTRAINTS": "BATASAN", "ACTION_CONSTRAINT": "BATASAN_AKSI",
    "ACTION_CONSTRAINTS": "BATASAN_AKSI", "SYMMETRY": "SIMETRI", "VIEW": "TAMPILAN",
    "CHECK_DEADLOCK": "CEK_KEBUNTUAN",
}
# standard modules and the Indonesian wrapper that re-exports them
STD = {
    "Naturals": ("BilanganAsli", {"Nat": "Asli"}),
    "Integers": ("BilanganBulat", {"Nat": "Asli", "Int": "Bulat"}),
    "Sequences": ("Barisan", {"Seq": "Barisan", "Len": "Panjang", "Head": "Kepala", "Tail": "Ekor",
                               "Append": "Tambahkan", "SubSeq": "SubBarisan", "SelectSeq": "SaringBarisan"}),
    "FiniteSets": ("HimpunanHingga", {"Cardinality": "Kardinalitas", "IsFiniteSet": "Berhingga"}),
    "TLC": ("AlatTLC", {"Print": "Cetak", "PrintT": "CetakT", "Assert": "Tegaskan",
                        "ToString": "KeTeks", "Permutations": "Permutasi",
                        "RandomElement": "ElemenAcak", "SortSeq": "UrutkanBarisan"}),
}

# ---------------------------------------------------------------- lexer
SYMS = ["(\\X)", "(+)", "(-)", "(.)", "(/)", "-+->", "::=", "<=>", "|->", "...",
        "/\\", "\\/", "=>", "~>", "[]", "<<", ">>", "<>", "->", "<-", "==", ":=", ":>", "<:", "@@", "!!",
        "|-", "-|", "|=", "=|", "$$", "??", "^^", "&&", "##", "++", "--", "%%", "**", "//", "..",
        "<=", ">=", "=<", "/=", "^+", "^*", "^#", "||", "~"]
OPENERS = {"(": ")", "[": "]", "{": "}", "<<": ">>"}
CLOSERS = {")", "]", "}", ">>"}
WORD = re.compile(r"[A-Za-z0-9_]+")
BSWORD = re.compile(r"\\[A-Za-z]+")

def lex(lines):
    """Per line: list of (kind, text, col). kinds: ws, word, sym, str, cmt."""
    out, depth = [], 0
    for line in lines:
        toks, i, n = [], 0, len(line)
        while i < n:
            if depth:                                   # inside (* ... *), possibly nested
                j = i
                while j < n and depth:
                    if line.startswith("(*", j): depth += 1; j += 2
                    elif line.startswith("*)", j): depth -= 1; j += 2
                    else: j += 1
                toks.append(("cmt", line[i:j], i)); i = j; continue
            c = line[i]
            if c in " \t":
                j = i
                while j < n and line[j] in " \t": j += 1
                toks.append(("ws", line[i:j], i)); i = j; continue
            if line.startswith("\\*", i):
                toks.append(("cmt", line[i:], i)); break
            if line.startswith("(*", i):
                depth = 1; j = i + 2
                while j < n and depth:
                    if line.startswith("(*", j): depth += 1; j += 2
                    elif line.startswith("*)", j): depth -= 1; j += 2
                    else: j += 1
                toks.append(("cmt", line[i:j], i)); i = j; continue
            if c == '"':
                j = i + 1
                while j < n and line[j] != '"':
                    j += 2 if line[j] == "\\" else 1
                j = min(j + 1, n)
                toks.append(("str", line[i:j], i)); i = j; continue
            m = WORD.match(line, i)
            if m:
                toks.append(("word", m.group(), i)); i = m.end(); continue
            m = BSWORD.match(line, i)
            if m:
                toks.append(("sym", m.group(), i)); i = m.end(); continue
            for s in SYMS:
                if line.startswith(s, i):
                    toks.append(("sym", s, i)); i += len(s); break
            else:
                toks.append(("sym", c, i)); i += 1
        out.append(toks)
    return out

def first_code(toks):
    for t in toks:
        if t[0] != "ws":
            return t
    return None

# ---------------------------------------------------------------- Indonesian -> TLA+
class TlaidError(Exception):
    pass

def next_code(lexed, li, i):
    """The next token after lexed[li][i] that is not whitespace or a comment, or None."""
    for lj in range(li, len(lexed)):
        start = i + 1 if lj == li else 0
        for t in lexed[lj][start:]:
            if t[0] not in ("ws", "cmt"):
                return t
    return None

def new_frame(kind, start=None):
    return {"k": kind, "exc": False, "start": start, "base": None, "base_src": "", "expect": False}

def code_between(lexed, a, b):
    """Texts of the code tokens strictly between positions a and b, each (line index, token index)."""
    out = []
    for li in range(a[0], b[0] + 1):
        lo = a[1] + 1 if li == a[0] else 0
        hi = b[1] if li == b[0] else len(lexed[li])
        out += [t[1] for t in lexed[li][lo:hi] if t[0] not in ("ws", "cmt")]
    return out

TLA_RESERVED = {"ASSUME", "ASSUMPTION", "AXIOM", "BOOLEAN", "CASE", "CHOOSE", "CONSTANT", "CONSTANTS",
                "DOMAIN", "ELSE", "ENABLED", "EXCEPT", "EXTENDS", "IF", "IN", "INSTANCE", "LET", "LOCAL",
                "MODULE", "OTHER", "STRING", "SUBSET", "THEN", "THEOREM", "UNCHANGED", "UNION", "VARIABLE",
                "VARIABLES", "WITH", "TRUE", "FALSE", "LAMBDA", "RECURSIVE", "LEMMA", "PROPOSITION", "COROLLARY"}
OPERAND_END = {")", "]", "}", "'", ">>"}

def is_name(t):
    return (t[0] == "word" and t[1] not in SPEC_KW and t[1] not in TLA_RESERVED
            and not t[1][0].isdigit() and not t[1].startswith(("ADIL_", "WF_", "SF_", "_")))

def postfix_tetap(toks, fname, ln):
    """'x TETAP' and '<<a, b>> TETAP' on one line: {index of the first operand token: index of TETAP}."""
    segs, code = {}, [k for k, t in enumerate(toks) if t[0] not in ("ws", "cmt")]
    bad = "TETAP di belakang hanya untuk satu nama variabel atau <<...>> berisi nama variabel di baris yang sama"
    for n, k in enumerate(code):
        if toks[k][0] != "word" or toks[k][1] != "TETAP" or n == 0:
            continue
        tp = toks[code[n - 1]]
        if is_name(tp):
            if n >= 2 and toks[code[n - 2]][1] in (".", "!"):
                raise TlaidError(f"{fname}:{ln}:{toks[k][2] + 1}: {bad}")
            segs[code[n - 1]] = k
        elif tp[1] == ">>":
            depth, q = 0, None
            for m in range(n - 1, -1, -1):
                t = toks[code[m]][1]
                depth += (t == ">>") - (t == "<<")
                if depth == 0:
                    q = m; break
            if q is None or not all(is_name(toks[code[m]]) or toks[code[m]][1] == "," for m in range(q + 1, n - 1)):
                raise TlaidError(f"{fname}:{ln}:{toks[k][2] + 1}: {bad}")
            segs[code[q]] = k
        elif tp[1] in OPERAND_END or tp[0] == "str" or (tp[0] == "word" and tp[1][0].isdigit()):
            raise TlaidError(f"{fname}:{ln}:{toks[k][2] + 1}: {bad}")
    return segs                                       # anything else: TETAP in front, as in TLA+

def to_tla(src, fname="spec.tlaid"):
    lines = src.split("\n")
    lexed = lex(lines)
    out, shifts, stack, shifted_bullets = [], {}, [], []
    frames = [new_frame("root")]                     # open brackets
    # stack entries: [what, line, bracket depth, state]; KASUS state is "panah" (waiting for MAKA) or "nilai"
    def drop_finished_kasus():
        while stack and stack[-1][0] == "KASUS" and stack[-1][3] == "nilai":
            stack.pop()
    def kasus_ends_here(ln):
        for e in stack:
            if e[0] == "KASUS" and e[3] == "panah":
                raise TlaidError(f"{fname}:{e[1]}: KASUS di baris {e[1]} belum punya MAKA")
        stack[:] = [e for e in stack if e[0] != "KASUS"]
    for ln, toks in enumerate(lexed, 1):
        line = lines[ln - 1]
        delta, pieces, cmap, groups, outcol, cause, last_code = 0, [], [], [], 0, None, None
        t0 = first_code(toks)
        if t0 is not None and t0[0] != "cmt" and t0[2] == 0:
            frames = [new_frame("root")]              # a new definition starts
            kasus_ends_here(ln)
        segs = postfix_tetap(toks, fname, ln)
        i = 0
        while i < len(toks):
            kind, text, col = toks[i]
            if kind == "ws":
                take = min(delta, len(text) - 1) if i + 1 < len(toks) else min(delta, len(text))
                delta -= take; piece = text[take:]
                pieces.append(piece); outcol += len(piece); i += 1; continue
            if i in segs:                             # 'x TETAP' -> 'UNCHANGED x': the one reordering
                k = segs[i]
                last = max(m for m in range(i, k) if toks[m][0] not in ("ws", "cmt"))
                rep = "UNCHANGED " + line[col:toks[last][2] + len(toks[last][1])]
                width = toks[k][2] + len("TETAP") - col
                cmap.append((col, outcol))
                if len(rep) <= width:
                    pad = width - len(rep); take = min(delta, pad); delta -= take
                    piece = rep + " " * (pad - take)
                else:
                    piece = rep; delta += len(rep) - width; cause = ("TETAP", "UNCHANGED")
                groups.append([col, col + width, outcol, outcol + len(rep)])
                pieces.append(piece); outcol += len(piece); i = k + 1; last_code = "TETAP"; continue
            cmap.append((col, outcol))
            rep, width = None, len(text)
            top = frames[-1]
            if top["expect"] and kind != "cmt":       # a change inside [f KECUALI ...] starts here
                top["expect"] = False
                if text != "!":                       # '!' : plain TLA+ written by hand, leave it
                    base = top["base"]
                    code = [k for k in range(i, len(toks)) if toks[k][0] not in ("ws", "cmt")]
                    shown = top["base_src"]
                    if (len(code) <= len(base) or [toks[k][1] for k in code[:len(base)]] != base
                            or toks[code[len(base)]][1] not in ("[", ".")):
                        hint = (f"misalnya [{shown} KECUALI {shown}[x] = 0]" if len(base) == 1 else
                                f"atau beri nama dulu, misalnya MISALKAN f == {shown} MAKA [f KECUALI f[x] = 0]")
                        raise TlaidError(f"{fname}:{ln}:{col + 1}: setiap perubahan di KECUALI diawali {shown}, "
                                         f"sama persis dengan yang tertulis sebelum KECUALI, lalu [..] atau .nama; {hint}")
                    last = code[len(base) - 1]
                    width = toks[last][2] + len(toks[last][1]) - col
                    take = min(delta, width - 1); delta -= take
                    piece = " " * (width - 1 - take) + "!"   # the path keeps its column: seen[r] -> ___![r]
                    pieces.append(piece); outcol += len(piece); i = last + 1; last_code = "!"; continue
            if kind == "word":
                # two-word phrases: TIDAK DALAM, BAGIAN DARI, UNTUK SEMUA
                if (i + 2 < len(toks) and toks[i + 1][0] == "ws"
                        and (text, toks[i + 2][1]) in PHRASES and toks[i + 2][0] == "word"):
                    rep = PHRASES[(text, toks[i + 2][1])]
                    width = len(text) + len(toks[i + 1][1]) + len(toks[i + 2][1]); i += 2
                elif any(text.startswith(p) for p in FAIR):  # older spelling ADIL_LEMAH_vars(A)
                    p = next(p for p in FAIR if text.startswith(p))
                    pad = len(p) - len(FAIR[p]); take = min(delta, pad); delta -= take
                    piece = FAIR[p] + " " * (pad - take) + text[len(p):]
                    pieces.append(piece); outcol += len(piece); i += 1; last_code = text; continue
                elif (text in ("ATAU", "DAN") and i + 2 < len(toks) and toks[i + 1][0] == "ws"
                        and toks[i + 2][1] == ("STUTTERING" if text == "ATAU" else "BERUBAH")):
                    # the subscript of [A]_v (ATAU STUTTERING v) and <<A>>_v (DAN BERUBAH v)
                    word, closer = toks[i + 2][1], ("]" if text == "ATAU" else ">>")
                    joined = "".join(pieces); body = joined.rstrip(" ")
                    if last_code != closer or not body.endswith(closer):
                        example = "[Next] ATAU STUTTERING vars" if text == "ATAU" else "<<A>> DAN BERUBAH vars"
                        raise TlaidError(f"{fname}:{ln}:{col + 1}: {text} {word} hanya boleh langsung "
                                         f"setelah {closer}, misalnya {example}")
                    width = toks[i + 2][2] + len(word) - col
                    pad = len(joined) - len(body) + width - 1; take = min(delta, pad); delta -= take
                    piece = "_" + " " * (pad - take)
                    pieces = [body, piece]; cmap[-1] = (col, len(body)); outcol = len(body) + len(piece)
                    i += 3; last_code = word; continue
                elif text in ("STUTTERING", "BERUBAH"):
                    raise TlaidError(f"{fname}:{ln}:{col + 1}: {text} hanya dipakai dalam [A] ATAU STUTTERING v "
                                     f"atau <<A>> DAN BERUBAH v")
                elif text == "TERHADAP":                 # WF_v / SF_v: ADIL_LEMAH TERHADAP v (A)
                    joined = "".join(pieces); body = joined.rstrip(" ")
                    if last_code in ("]", ">>"):
                        raise TlaidError(f"{fname}:{ln}:{col + 1}: subskrip aksi kini ditulis "
                                         f"[A] ATAU STUTTERING v atau <<A>> DAN BERUBAH v; TERHADAP hanya "
                                         f"untuk ADIL_LEMAH TERHADAP v (A) dan ADIL_KUAT TERHADAP v (A)")
                    if last_code not in ("ADIL_LEMAH", "ADIL_KUAT") or not body.endswith(("WF", "SF")):
                        raise TlaidError(f"{fname}:{ln}:{col + 1}: TERHADAP harus langsung mengikuti "
                                         f"ADIL_LEMAH atau ADIL_KUAT di baris yang sama")
                    pad = len(joined) - len(body) + width - 1; take = min(delta, pad); delta -= take
                    piece = "_" + " " * (pad - take)
                    pieces = [body, piece]; cmap[-1] = (col, len(body)); outcol = len(body) + len(piece)
                    i += 1; last_code = text; continue
                elif text in SPEC_KW:
                    if text == "KECUALI":
                        top["exc"] = True
                        if top["start"] is not None:
                            top["base"] = code_between(lexed, top["start"], (ln - 1, i))
                            top["expect"] = bool(top["base"])
                            sl, sc = top["start"]
                            top["base_src"] = (line[lexed[sl][sc][2] + 1:col].strip() if sl == ln - 1
                                               else " ".join(top["base"]))
                    elif text == "BERNILAI":
                        top = frames[-1]
                        rep = "|->" if top["k"] == "[" and not top["exc"] else ":>"
                    elif text in ("ADIL_LEMAH", "ADIL_KUAT"):
                        nxt = next_code(lexed, ln - 1, i)
                        if nxt is None or nxt[1] != "TERHADAP":
                            raise TlaidError(f"{fname}:{ln}:{col + 1}: {text} harus diikuti TERHADAP dan subskripnya, "
                                             f"misalnya {text} TERHADAP vars (Next)")
                    if text in BULLETS_ID and delta:
                        shifted_bullets.append((ln, col, delta, text, cause))
                    if text == "JIKA": stack.append(["JIKA", ln, 0, ""])
                    elif text == "MISALKAN": stack.append(["MISALKAN", ln, 0, ""])
                    elif text == "KASUS": stack.append(["KASUS", ln, len(frames), "panah"])
                    elif text == "LAINNYA":
                        if stack and stack[-1][0] == "KASUS": stack[-1][3] = "panah"
                    elif text == "SELALU":
                        if stack and stack[-1][0] == "KASUS" and stack[-1][3] == "nilai": stack[-1][3] = "panah"
                    elif text == "MAKA":
                        drop_finished_kasus()
                        if stack and stack[-1][0] == "KASUS":
                            rep = "->"; stack[-1][3] = "nilai"
                        elif not stack or stack[-1][0] == "JIKA-MAKA":
                            raise TlaidError(f"{fname}:{ln}:{col + 1}: MAKA tanpa JIKA, MISALKAN atau KASUS yang masih terbuka")
                        else:
                            opener = stack.pop()
                            if opener[0] == "JIKA":
                                rep = "THEN"; stack.append(["JIKA-MAKA", opener[1], 0, ""])
                            else:
                                rep = "IN"
                    elif text == "SEBALIKNYA":
                        drop_finished_kasus()
                        if stack and stack[-1][0] == "JIKA":
                            raise TlaidError(f"{fname}:{ln}:{col + 1}: JIKA di baris {stack[-1][1]} belum punya MAKA sebelum SEBALIKNYA ini")
                        if not stack or stack[-1][0] != "JIKA-MAKA":
                            raise TlaidError(f"{fname}:{ln}:{col + 1}: SEBALIKNYA tanpa JIKA ... MAKA sebelumnya")
                        stack.pop()
                    rep = rep or SPEC_KW[text]
                elif text == "EXCEPT":
                    frames[-1]["exc"] = True
                elif text in ("IF", "LET"):               # English keywords still work
                    stack.append(["JIKA" if text == "IF" else "MISALKAN", ln, 0, ""])
                elif text == "CASE":
                    stack.append(["KASUS", ln, len(frames), "panah"])
                elif text == "OTHER":
                    if stack and stack[-1][0] == "KASUS": stack[-1][3] = "panah"
                elif text in ("THEN", "IN"):
                    drop_finished_kasus()
                    if stack:
                        opener = stack.pop()
                        if opener[0] == "JIKA": stack.append(["JIKA-MAKA", opener[1], 0, ""])
                elif text == "ELSE":
                    drop_finished_kasus()
                    if stack and stack[-1][0] == "JIKA-MAKA": stack.pop()
            elif kind == "sym":
                if text in BULLETS_TLA and delta:
                    shifted_bullets.append((ln, col, delta, text, cause))
                if stack and stack[-1][0] == "KASUS":
                    if text == "->" and stack[-1][3] == "panah": stack[-1][3] = "nilai"
                    elif text == "[]" and stack[-1][3] == "nilai": stack[-1][3] = "panah"
                if text == "," and top["base"]:
                    top["expect"] = True              # the next change of this KECUALI
                if text in OPENERS:
                    frames.append(new_frame(text, (ln - 1, i)))
                elif text in CLOSERS and len(frames) > 1:
                    frames.pop()
                    while stack and stack[-1][0] == "KASUS" and stack[-1][2] > len(frames):
                        stack.pop()
            if kind != "cmt":
                last_code = text
            if rep is None:
                pieces.append(text); outcol += len(text); i += 1; continue
            if len(rep) <= width:
                pad = width - len(rep); take = min(delta, pad); delta -= take
                pieces.append(rep)
                if pad - take: pieces.append(" " * (pad - take))
                piece = ""
            else:
                piece = rep; delta += len(rep) - width; cause = (text, rep)
            pieces.append(piece); outcol = len("".join(pieces)); i += 1
        if groups or any(s != o for s, o in cmap):
            shifts[ln] = {"t": cmap, "g": groups}
        out.append("".join(pieces))
    stack[:] = [e for e in stack if not (e[0] == "KASUS" and e[3] == "nilai")]
    if stack:
        what, ln = stack[-1][0], stack[-1][1]
        need = "SEBALIKNYA" if what == "JIKA-MAKA" else "MAKA"
        raise TlaidError(f"{fname}:{ln}: {what.split('-')[0]} di baris {ln} belum ditutup dengan {need}")
    # a bullet that moved is only a problem if a later line lines up a bullet under it
    for ln, col, d, word, cause in shifted_bullets:
        for later in lexed[ln:]:
            t = first_code(later)
            if t is None or t[0] == "cmt":
                continue
            if t[2] == 0:
                break
            if t[2] == col and (t[1] in BULLETS_ID or t[1] in BULLETS_TLA):
                raise TlaidError(f"{fname}:{ln}:{col + 1}: {word} ini akan bergeser {d} kolom karena "
                                 f"{cause[0]} menjadi {cause[1]} yang lebih panjang, padahal ada {word} di "
                                 f"bawahnya pada kolom yang sama. Mulai daftar {word} ini di baris baru.")
    return "\n".join(out), shifts

def cfg_to_tla(src):
    out = []
    for toks in lex(src.split("\n")):
        pieces, seen_code = [], False
        for kind, text, col in toks:
            if kind == "word" and not seen_code and text in CFG_KW:
                text = CFG_KW[text]
            elif kind == "word" and text in CFG_VALUES:
                text = CFG_VALUES[text]
            if kind != "ws":
                seen_code = True
            pieces.append(text)
        out.append("".join(pieces))
    return "\n".join(out)

# ---------------------------------------------------------------- TLA+ -> Indonesian
def glued(ta, na, tb, nb):
    """1 if two tokens that touched in TLA+ need a space once translated, else 0."""
    left_word, right_word = re.search(r"\w$", na), re.match(r"\w", nb)
    if left_word and right_word: return 1
    is_kw = lambda x: bool(x) and (x.split()[0] in SPEC_KW or x.startswith("ADIL_"))
    if left_word and na != ta and is_kw(na) and not nb.startswith((",", ")", "]", "}", ">>", ";")):
        return 1                                        # MUNGKIN(x) -> MUNGKIN (x), but {BENAR, SALAH}
    if right_word and nb != tb and is_kw(nb) and not na.endswith(("(", "[", "{", "<<")):
        return 1                                        # x):>1 -> x) BERNILAI 1, but (SUBSET S -> (HIMPUNAN_KUASA S
    if na.startswith("ADIL_") and nb.startswith("("): return 1  # ADIL_LEMAH TERHADAP vars (Next)
    return 0

def to_tlaid(src, renames=None, colmap=None):
    """TLA+ -> TLA-ID. If colmap is a dict, it receives {line: [(src_start, src_end, new_start, new_end), ...]}."""
    renames = renames or {}
    lines = src.split("\n")
    lexed = lex(lines)
    # ---- pass 1: decide the Indonesian word for each token, using bracket context
    code = [(li, j) for li, toks in enumerate(lexed) for j, t in enumerate(toks) if t[0] not in ("ws", "cmt")]
    tok = lambda q: lexed[q[0]][q[1]]
    nt, span, drop = {}, {}, set()                  # new text; merged source span end; absorbed tokens
    def frame(kind, open_n=None):
        return {"k": kind, "exc": False, "case": False, "pend": [], "in": False, "open": open_n, "base": None}
    def render(ns):                                 # TLA-ID text of the code tokens code[n] for n in ns
        s, prev = "", None
        for m in ns:
            q2 = code[m]
            if q2 in drop: continue
            t = tok(q2); new_t = nt.get(q2, t[1])
            if prev is not None:
                pt = tok(code[prev]); gap = 1
                if code[prev][0] == q2[0]:
                    gap = max(t[2] - (pt[2] + len(pt[1])), glued(pt[1], nt.get(code[prev], pt[1]), t[1], new_t))
                s += " " * gap
            s += new_t; prev = m
        return s
    except_bangs = {}                               # ! of an EXCEPT change -> (its frame, its column)
    frames = [frame("root")]
    def match_close(n):                             # index in `code` of the ] matching the [ at code[n]
        depth = 0
        for m in range(n, len(code)):
            t = tok(code[m])[1]
            if t == "[": depth += 1
            elif t == "]":
                depth -= 1
                if depth == 0: return m
        return None
    def impor_tetap(n):
        """UNCHANGED x -> x TETAP ;  UNCHANGED <<a, b>> -> <<a, b>> TETAP  (same line, names only)."""
        q = code[n]
        if n + 1 >= len(code) or code[n + 1][0] != q[0]:
            return False
        a = code[n + 1]; ta = tok(a); last = None
        if is_name(ta):
            nxt = tok(code[n + 2]) if n + 2 < len(code) and code[n + 2][0] == q[0] else None
            if nxt is None or nxt[1] not in (".", "[", "(", "'"):
                last = n + 1
        elif ta[1] == "<<":
            depth = 0
            for m in range(n + 1, len(code)):
                if code[m][0] != q[0]:
                    return False
                t = tok(code[m])
                depth += (t[1] == "<<") - (t[1] == ">>")
                if depth == 0:
                    last = m; break
                if m > n + 1 and not (is_name(t) or t[1] in (",", "<<")):
                    return False
        if last is None:
            return False
        lt = tok(code[last]); end = lt[2] + len(lt[1])
        nt[q] = lines[q[0]][ta[2]:end] + " TETAP"; span[q] = end
        for m in range(n + 1, last + 1):
            drop.add(code[m])
        return True
    for n, q in enumerate(code):
        kind, text, col = tok(q)
        if col == 0 and (n == 0 or code[n - 1][0] != q[0]):
            frames = [frame("root")]                # a new definition starts
        top = frames[-1]
        if q in nt or q in drop:
            pass
        elif kind == "word" and text == "UNCHANGED" and impor_tetap(n):
            pass
        elif kind == "word" and text.startswith("_") and n > 0 and tok(code[n - 1])[1] in ("]", ">>") \
                and code[n - 1][0] == q[0] and tok(code[n - 1])[2] + len(tok(code[n - 1])[1]) == col:
            word = "ATAU STUTTERING " if tok(code[n - 1])[1] == "]" else "DAN BERUBAH "
            nt[q] = (word + text[1:]).strip()            # [Next]_vars -> [Next] ATAU STUTTERING vars
        elif kind == "word":
            if text == "CASE": top["case"] = True
            if text == "EXCEPT":
                top["exc"] = True
                if top["open"] is not None:
                    top["base"] = render(range(top["open"] + 1, n))
            if text == "CHOOSE": top["pend"].append("E")
            if text == "LAMBDA": top["pend"].append("L")
            if text in REV_WORD: nt[q] = REV_WORD[text]
            elif text in renames: nt[q] = renames[text]
            elif text.startswith("WF_"): nt[q] = ("ADIL_LEMAH TERHADAP " + text[3:]).strip()
            elif text.startswith("SF_"): nt[q] = ("ADIL_KUAT TERHADAP " + text[3:]).strip()
        elif kind == "sym":
            if text == "\\A": top["pend"].append("A")
            elif text == "\\E": top["pend"].append("E")
            elif text == "\\in" and top["k"] == "{" and not top["pend"]: top["in"] = True
            if text == ":":
                if top["pend"]:
                    nt[q] = {"A": "BERLAKU", "E": "SEHINGGA", "L": ":"}[top["pend"].pop()]
                elif top["k"] == "{":
                    nt[q] = "SEHINGGA" if top["in"] else "UNTUK"
            elif text == "|->":
                nt[q] = "BERNILAI"
            elif text == ":>":
                if not (top["k"] == "[" and not top["exc"]): nt[q] = "BERNILAI"
            elif text == "@@":
                nt[q] = "SERTA"
            elif text == "@":
                nt[q] = "LAMA"
            elif text == "->":
                if top["case"]: nt[q] = "MAKA"
                elif top["k"] == "[" and not top["exc"]: nt[q] = "KE"
            elif text == "[]":
                if not top["case"]: nt[q] = "SELALU"
            elif (text == "!" and n > 0 and top["exc"] and top["base"] and tok(code[n - 1])[1] in ("EXCEPT", ",")
                    and n + 1 < len(code) and tok(code[n + 1])[1] in ("[", ".")):
                nt[q] = top["base"]; except_bangs[q] = (id(top), col)   # ![r] = v  ->  seen[r] = v
            elif text in REV_SYM:
                nt[q] = REV_SYM[text]
            if text in OPENERS:
                frames.append(frame(text, n))
            elif text in CLOSERS and len(frames) > 1:
                frames.pop()
    # a change that continues on the next line, lined up under the first one, stays lined up
    line_first = {}
    for q2 in code:
        line_first.setdefault(q2[0], q2)
    starts_line = {(fid, c) for q2, (fid, c) in except_bangs.items() if line_first[q2[0]] == q2}
    except_starts = {q2 for q2, key in except_bangs.items() if key in starts_line}
    # ---- rows for layout: (column, source text, new text) per non-whitespace token
    new = []
    for li, toks in enumerate(lexed):
        row = []
        for j, (kind, text, col) in enumerate(toks):
            q = (li, j)
            if kind == "ws" or q in drop:
                continue
            src_text = lines[li][col:span[q]] if q in span else text
            row.append((col, src_text, nt.get(q, text), text in BULLETS_TLA or q in except_starts))
        new.append(row)
    # blocks start at lines whose first token is in column 0
    blocks, cur = [], []
    for idx, row in enumerate(new):
        if row and row[0][0] == 0 and cur:
            blocks.append(cur); cur = []
        cur.append(idx)
    if cur: blocks.append(cur)
    out = [""] * len(lines)
    bullets = BULLETS_TLA
    for blk in blocks:
        # significant columns: the first token of every line and every junction bullet
        sig = {}
        for i in blk:
            for j, (col, text, nt, al) in enumerate(new[i]):
                if j == 0 or al:
                    sig.setdefault(col, []).append((i, j))
        f, prev = {}, None
        def natural(i, j):
            row = new[i]
            k = max(m for m in range(j) if m == 0 or row[m][3])   # previous significant token
            pos = f[row[k][0]]
            for m in range(k + 1, j + 1):
                (ca, ta, na, _), (cb, tb, nb, _) = row[m - 1], row[m]
                gap = max(cb - (ca + len(ta)), glued(ta, na, tb, nb))
                pos += len(na) + gap
            return pos
        for col in sorted(sig):
            cand = [col if prev is None else f[prev] + (col - prev)]
            cand += [natural(i, j) for i, j in sig[col] if j > 0]
            f[col] = max(cand); prev = col
        for i in blk:
            s, row = "", new[i]
            for j, (col, text, nt, al) in enumerate(row):
                if j == 0 or al:
                    s += " " * (f[col] - len(s))
                else:
                    (ca, ta, na, _) = row[j - 1]
                    gap = max(col - (ca + len(ta)), glued(ta, na, text, nt))
                    s += " " * gap
                if colmap is not None:
                    colmap.setdefault(i + 1, []).append((col, col + len(text), len(s), len(s) + len(nt)))
                s += nt
            out[i] = s
    return "\n".join(out)

def cfg_to_tlaid(src):
    out = []
    for toks in lex(src.split("\n")):
        pieces, seen = [], False
        for kind, text, col in toks:
            if kind == "word" and not seen and text in REV_CFG: text = REV_CFG[text]
            elif kind == "word" and text in ("TRUE", "FALSE"): text = REV_WORD[text]
            if kind != "ws": seen = True
            pieces.append(text)
        out.append("".join(pieces))
    return "\n".join(out)

# ---------------------------------------------------------------- wrapper modules
def wrapper_modules():
    mods = {}
    for std, (name, ops) in STD.items():
        ext = [std] + (["BilanganAsli"] if name == "BilanganBulat" else [])
        body = []
        for en, idn in ops.items():
            if name == "BilanganBulat" and en == "Nat":
                continue
            arity = {"Seq": "S", "Len": "s", "Head": "s", "Tail": "s", "Append": "s, e",
                     "SubSeq": "s, m, n", "Cardinality": "S", "IsFiniteSet": "S", "Print": "out, val",
                     "PrintT": "out", "Assert": "val, out", "ToString": "v", "Permutations": "S",
                     "RandomElement": "S"}.get(en)
            if en == "SelectSeq":
                body.append(f"{idn}(s, Test(_)) == SelectSeq(s, Test)")
            elif en == "SortSeq":
                body.append(f"{idn}(s, Op(_, _)) == SortSeq(s, Op)")
            elif arity:
                body.append(f"{idn}({arity}) == {en}({arity})")
            else:
                body.append(f"{idn} == {en}")
        mods[name] = (f"---- MODULE {name} ----\n\\* TLA-ID: nama Indonesia untuk modul {std}\n"
                      f"EXTENDS {', '.join(ext)}\n\n" + "\n".join(body) + "\n====\n")
    return mods

# ---------------------------------------------------------------- TLC output -> Indonesian
MSG = [
    (r"^Model checking completed\. No error has been found\.", "Pemeriksaan model selesai. Tidak ada kesalahan yang ditemukan."),
    (r"^Error: Invariant (\S+) is violated\.", r"Kesalahan: Invarian \1 dilanggar."),
    (r"^Error: Invariant (\S+) is violated by the initial state:", r"Kesalahan: Invarian \1 dilanggar oleh keadaan awal:"),
    (r"^Error: Action property (.+) is violated\.", r"Kesalahan: Properti aksi \1 dilanggar."),
    (r"^Error: Temporal properties (.+) and (.+) were violated\.", r"Kesalahan: Properti temporal \1 dan \2 dilanggar."),
    (r"^Error: Temporal property (.+) was violated\.", r"Kesalahan: Properti temporal \1 dilanggar."),
    (r"^Error: Assumption (.+) is false\.", r"Kesalahan: Asumsi \1 bernilai SALAH."),
    (r"^Error: Successor state is not completely specified by action (\S+) of the",
     r"Kesalahan: Keadaan berikutnya tidak ditentukan sepenuhnya oleh aksi \1 dari"),
    (r"^next-state relation\. The following variables? (?:is|are) not defined: (.*)\.",
     r"relasi langkah berikutnya. Variabel berikut tidak didefinisikan: \1."),
    (r"^Error: TLC cannot handle the temporal formula (.*)", r"Kesalahan: TLC tidak dapat menangani formula temporal \1"),
    (r"^Error: The specification contains more than one conjunct of the form \[\]\[Next\]_v,",
     "Kesalahan: Spesifikasi berisi lebih dari satu konjungsi berbentuk SELALU [Next] ATAU STUTTERING v,"),
    (r"^but TLC can handle only specifications with one next-state relation\.",
     "padahal TLC hanya dapat menangani spesifikasi dengan satu relasi langkah berikutnya."),
    (r"^This was probably caused by an error in the spec or model\.", "Ini kemungkinan besar disebabkan oleh kesalahan di spesifikasi atau model."),
    (r"^See the User Output or TLC Console for clues to what happened\.", "Lihat User Output atau TLC Console untuk petunjuk apa yang terjadi."),
    (r"^The exception was a (.*)", r"Pengecualiannya adalah \1"),
    (r"^Could not find declaration or definition of symbol '(.*)'\.", r"Tidak menemukan deklarasi atau definisi simbol '\1'."),
    (r"^Error: Evaluating invariant (\S+) failed\.", r"Kesalahan: Evaluasi invarian \1 gagal."),
    (r"^Error: Evaluating assumption (.+) failed\.", r"Kesalahan: Evaluasi asumsi \1 gagal."),
    (r"^Error: The behavior up to this point is:", "Kesalahan: Perilaku sampai titik ini adalah:"),
    (r"^Error: The following behavior constitutes a counter-example:", "Kesalahan: Perilaku berikut adalah contoh penyangkal:"),
    (r"^Error: Deadlock reached\.", "Kesalahan: Terjadi kebuntuan (deadlock)."),
    (r"^Error: Temporal properties were violated\.", "Kesalahan: Properti temporal dilanggar."),
    (r"^Error: Parsing or semantic analysis failed\.", "Kesalahan: Penguraian atau analisis semantik gagal."),
    (r"^Error: (.*)", r"Kesalahan: \1"),
    (r"^State (\d+): <Initial predicate>", r"Keadaan \1: <Predikat awal>"),
    (r"^State (\d+): Stuttering", r"Keadaan \1: Diam (stuttering)"),
    (r"^State (\d+):(\s+)<(.*)>", r"Keadaan \1:\2<\3>"),
    (r"^Back to state (\d+): <(.*)>", r"Kembali ke keadaan \1: <\2>"),
    (r"^Back to state (\d+)", r"Kembali ke keadaan \1"),
    (r"^(\d+) states? generated, (\d+) distinct states? found, (\d+) states? left on queue\.",
     r"\1 keadaan dihasilkan, \2 keadaan berbeda ditemukan, \3 keadaan tersisa di antrean."),
    (r"^The depth of the complete state graph search is (\d+)\.", r"Kedalaman pencarian graf keadaan adalah \1."),
    (r"^Finished computing initial states: (\d+) distinct states? generated at (.*)\.",
     r"Selesai menghitung keadaan awal: \1 keadaan berbeda dihasilkan pada \2."),
    (r"^Computing initial states\.\.\.", "Menghitung keadaan awal..."),
    (r"^Starting\.\.\. \((.*)\)", r"Mulai... (\1)"),
    (r"^Finished in (\S+) at \((.*)\)", r"Selesai dalam \1 pada (\2)"),
    (r"^Checking temporal properties for the complete state space with (\d+) total distinct states at \((.*)\)",
     r"Memeriksa properti temporal untuk seluruh ruang keadaan (\1 keadaan berbeda) pada (\2)"),
    (r"^Checking (\d+) branches of temporal properties for the complete state space with (\d+) total distinct states at \((.*)\)",
     r"Memeriksa \1 cabang properti temporal untuk seluruh ruang keadaan (\2 keadaan berbeda) pada (\3)"),
    (r"^Finished checking temporal properties in (\S+) at (.*)", r"Selesai memeriksa properti temporal dalam \1 pada \2"),
    (r"^The error occurred when TLC was evaluating the nested", "Kesalahan terjadi saat TLC mengevaluasi ekspresi bertingkat"),
    (r"^expressions at the following positions:", "pada posisi berikut:"),
    (r"^Attempted to apply function:", "Mencoba menerapkan fungsi:"),
    (r"^to argument (.*), which is not in the domain of the function\.", r"ke argumen \1, yang tidak ada dalam domain fungsi."),
    (r"^Parsing file (.*)", r"Mengurai berkas \1"),
    (r"^Semantic processing of module (\S+)", r"Pemrosesan semantik modul \1"),
    (r"^\*\*\*Parse Error\*\*\*", "***Kesalahan Penguraian***"),
    (r"^Fatal errors while parsing TLA\+ spec in file (\S+)", r"Kesalahan fatal saat mengurai spesifikasi di berkas \1"),
    (r"^Could not parse module (\S+) from file (.*)", r"Modul \1 tidak dapat diurai dari berkas \2"),
    (r"^Unknown operator: `(.*)'\.", r"Operator tidak dikenal: `\1'."),
    (r"^Semantic errors:", "Kesalahan semantik:"),
    (r"^<> followed by action not of form <<A>>_v\.", "AKHIRNYA diikuti aksi yang tidak berbentuk <<A>> DAN BERUBAH v."),
    (r"^\[\] followed by action not of form \[A\]_v\.", "SELALU diikuti aksi yang tidak berbentuk [A] ATAU STUTTERING v."),
    (r"^Was expecting \"(.*)\"", r'Yang diharapkan: "\1"'),
    (r"^Trace exploration spec path: (.*)", r"Spesifikasi penelusuran jejak: \1"),
]
MSG += [
    (r"^Running breadth-first search Model-Checking with fp (\d+) and seed (\S+) with (\d+) workers? on (\d+) cores with (\d+)MB heap.*",
     r"Pemeriksaan model breadth-first (fp \1, seed \2) dengan \3 worker, \4 inti, heap \5MB"),
    (r"^Linting of module (\S+)", r"Pemeriksaan gaya modul \1"),
    (r"^The average outdegree of the complete state graph is (\d+) \(minimum is (\d+), the maximum (\d+) and the 95th percentile is (\d+)\)\.",
     r"Rata-rata derajat keluar graf keadaan adalah \1 (minimum \2, maksimum \3, persentil ke-95: \4)."),
    (r"^(\s*)Estimates of the probability that TLC did not check all reachable states",
     r"\1Perkiraan peluang TLC tidak memeriksa semua keadaan yang terjangkau"),
    (r"^(\s*)because two distinct states had the same fingerprint:", r"\1karena dua keadaan berbeda punya fingerprint yang sama:"),
    (r"^(\s*)calculated \(optimistic\):(.*)", r"\1dihitung (optimistis):\2"),
    (r"^Progress\((\d+)\) at (.*): (\d+) states? generated(.*), (\d+) distinct states? found(.*), (\d+) states? left on queue\.",
     r"Kemajuan(\1) pada \2: \3 keadaan dihasilkan\4, \5 keadaan berbeda ditemukan\6, \7 keadaan tersisa di antrean."),
    (r"^Implied-temporal checking--satisfiability problem has (\d+) branch(?:es)?\.",
     r"Pemeriksaan temporal tersirat: masalah keterpenuhan punya \1 cabang."),
    (r"^Error: The error occurred when TLC was evaluating the nested", "Kesalahan: Kesalahan terjadi saat TLC mengevaluasi ekspresi bertingkat"),
    (r"^Error: TLC threw an unexpected exception\.", "Kesalahan: TLC mengalami pengecualian yang tidak terduga."),
    (r"^Temporal property (\S+) was violated\.", r"Properti temporal \1 dilanggar."),
    (r"^Error: Temporal property (\S+) was violated\.", r"Kesalahan: Properti temporal \1 dilanggar."),
    (r"^: In evaluation, the identifier (\S+) is either undefined or not an operator\.",
     r": Saat evaluasi, pengenal \1 belum terdefinisi atau bukan operator."),
    (r"^: The current version of TLC does not support action composition\.\s+An incomplete implementation can be enabled via the (\S+) java property\.",
     r": Versi TLC ini belum mendukung komposisi aksi. Implementasi yang belum lengkap bisa diaktifkan lewat properti java \1."),
    (r"^Multiple declarations or definitions for symbol (\S+)\.\s*$", r"Deklarasi atau definisi ganda untuk simbol \1."),
    (r"^This duplicates the one at (.*)\.", r"Ini menduplikasi yang ada di \1."),
    (r"^Operator (\S+) already defined or declared\.", r"Operator \1 sudah didefinisikan atau dideklarasikan."),
    (r"^Multiply-defined symbol '(\S+)': this definition or declaration conflicts\s*$",
     r"Simbol '\1' didefinisikan ganda: definisi atau deklarasi ini bentrok"),
    (r"^with the one at (.*)\.", r"dengan yang ada di \1."),
    (r"^The operator (\S+) requires (\d+) arguments?\.", r"Operator \1 membutuhkan \2 argumen."),
    (r"^File name '(\S+)' does not match the name '(\S+)' of the top level module it contains\.",
     r"Nama berkas '\1' tidak cocok dengan nama '\2' milik modul utama di dalamnya."),
    (r"^Unknown location$", "Lokasi tidak diketahui"),
    (r"^A non-function \(a (\w+)\) was applied as a function\.", r"Nilai yang bukan fungsi (sebuah \1) diterapkan sebagai fungsi."),
    (r"^\*\*\* Warnings: (\d+)", r"*** Jumlah peringatan: \1"),
    (r"^Error: The constant parameter (\S+) is not assigned a value by the configuration file\.",
     r"Kesalahan: Parameter konstanta \1 tidak diberi nilai oleh file konfigurasi."),
    (r"^Error: The property (\S+) specified in the configuration file$", r"Kesalahan: Properti \1 yang disebut di file konfigurasi"),
    (r"^is not defined in the specification\.", "tidak didefinisikan di spesifikasi."),
    (r"^Error: TLC found an error in the configuration file at line (\d+)$", r"Kesalahan: TLC menemukan kesalahan di file konfigurasi pada baris \1"),
    (r"^It was expecting (.*), but did not find it\.", r"TLC mengharapkan \1, tetapi tidak menemukannya."),
]
MSG.sort(key=lambda m: m[0] == r"^Error: (.*)")            # the catch-all goes last
MSG = [(re.compile(a), b) for a, b in MSG]
MSG2 = [(re.compile(a), b) for a, b in [
    (r"^Residual stack trace follows:", "Jejak tumpukan sisa:"),
    (r"^Module definition starting", "Definisi modul mulai"),
    (r"^(\w[\w ]*) starting at", r"\1 dimulai at"),
    (r"^In module (\S+)", r"Di modul \1"),
    (r"^\*\*\* Errors: (\d+)", r"*** Jumlah kesalahan: \1"),
]]
NOISE = ("Warning: Please run the Java VM", "(Use the -nowarning option", "Picked up JAVA_TOOL_OPTIONS",
         "Pemrosesan semantik modul _TLCTrace", "Pemrosesan semantik modul TLCExt",
         "Pemeriksaan gaya modul _TLCTrace", "Pemeriksaan gaya modul TLCExt")
POS1 = re.compile(r"line (\d+), col (\d+) to line (\d+), col (\d+) of module (\w+)")
POS2 = re.compile(r"[Ll]ine (\d+), column (\d+) to line (\d+), column (\d+) in (\w+)")
POS3 = re.compile(r"at line (\d+), column (\d+)")
VALUE_WORDS = {"TRUE": "BENAR", "FALSE": "SALAH", "Nat": "Asli", "Int": "Bulat"}   # the sets print by name

def src_col(shifts, mod, line, col, end=False):
    """Map a 1-based TLC column on `line` back to the .tlaid file."""
    entry = shifts.get(mod, {}).get(str(line)) or shifts.get(mod, {}).get(line)
    if not entry:
        return col
    c0 = col - 1                                     # the map is 0-based
    for s0, s1, o0, o1 in entry.get("g", []):        # a reordered group (x TETAP): the whole group
        if o0 <= c0 < o1:
            return s1 if end else s0 + 1
    best = None
    for s, o in entry["t"]:
        if o <= c0:
            best = (s, o)
    return col if best is None else best[0] + (c0 - best[1]) + 1

def widen_end(srcs, mod, line, col):
    """An end column inside an Indonesian keyword is widened to the keyword's last column."""
    lines = srcs.get(mod)
    if not lines or line > len(lines):
        return col
    for m in re.finditer(r"[A-Za-z_]+", lines[line - 1]):
        if m.start() < col <= m.end() and m.group() in SPEC_KW:
            return m.end()
    return col

def keyword_at(srcs, mod, line, col):
    lines = srcs.get(mod)
    if not lines or line > len(lines):
        return None
    m = re.match(r"[A-Za-z_]+", lines[line - 1][col - 1:])
    return m.group() if m and m.group() in SPEC_KW else None

def translate_values(s):
    pieces = re.split(r'("(?:[^"\\]|\\.)*")', s)
    for k in range(0, len(pieces), 2):
        pieces[k] = re.sub(r"\b(TRUE|FALSE|Nat|Int)\b", lambda m: VALUE_WORDS[m.group(1)], pieces[k])
        pieces[k] = pieces[k].replace("|->", "BERNILAI").replace(":>", "BERNILAI").replace("@@", "SERTA")
        pieces[k] = re.sub(r"^(\s*)/\\ ", r"\1DAN ", pieces[k])
        pieces[k] = re.sub(r"^(\s*)\\/ ", r"\1ATAU ", pieces[k])
    return "".join(pieces)

def translate_output(text, shifts, srcs):
    out, in_state = [], False
    for line in text.split("\n"):
        stripped = line.lstrip()
        if not stripped:
            in_state = False
        header = re.match(r"^(State \d+:|Back to state)", line)
        if in_state and not header and not re.match(r"^(\s|/\\ |\\/ |[A-Za-z_]\w* = )", line):
            in_state = False                            # the trace is over: "Finished ...", "12 states generated ..."
        if (in_state and not header) or stripped.startswith("/\\ ") or stripped.startswith("\\/ "):
            out.append(translate_values(line)); continue
        if re.match(r"^(State \d+:|Back to state|Error: Invariant \S+ is violated by the initial state)", line):
            in_state = True
        for rx, rep in MSG:
            if rx.match(line):
                line = rx.sub(rep, line, count=1); break
        line = POS1.sub(lambda m: f"baris {m[1]}, kolom {src_col(shifts, m[5], int(m[1]), int(m[2]))} sampai "
                                  f"baris {m[3]}, kolom {widen_end(srcs, m[5], int(m[3]), src_col(shifts, m[5], int(m[3]), int(m[4]), end=True))}, modul {m[5]}", line)
        line = POS2.sub(lambda m: f"Baris {m[1]}, kolom {src_col(shifts, m[5], int(m[1]), int(m[2]))} sampai "
                                  f"baris {m[3]}, kolom {widen_end(srcs, m[5], int(m[3]), src_col(shifts, m[5], int(m[3]), int(m[4]), end=True))}, modul {m[5]}", line)
        mod = next(iter(srcs), None)
        enc = re.match(r'^Encountered "(.*?)" at line (\d+), column (\d+)(.*)', line)
        if enc:
            l, c = int(enc[2]), int(enc[3])
            kw = keyword_at(srcs, mod, l, c) or enc[1]
            rest = re.sub(r' and token "(.*?)"', lambda m: ' dan token "' + REV_SYM.get(m[1].replace("\\\\", "\\"), REV_WORD.get(m[1], m[1])) + '"', enc[4])
            line = f'Menemukan "{kw}" di baris {l}, kolom {c}{rest}'
        pc = re.match(r"^(\s*)Precedence conflict between ops (\S+) in block (.*) and (\S+)\.", line)
        if pc:
            idn = lambda op: REV_SYM.get(op, op)
            line = f"{pc[1]}Konflik presedensi antara operator {idn(pc[2])} di blok {pc[3]} dan {idn(pc[4])}. Tambahkan tanda kurung."
        if any(en in line for en, _ in REPL_PHRASES[1:]) and not line.startswith(("Kesalahan", "Keadaan")):
            for en, idn in REPL_PHRASES:
                line = line.replace(en, idn)
        elif re.match(r"^\s*(<<|\{|\(|\[|:)", line) or re.search(r"(\|->|:>|@@)", line) \
                or line.startswith(("Keadaan ", "Kembali ke keadaan")):
            line = translate_values(line)
        for rx, rep in MSG2:
            line = rx.sub(rep, line)
        line = re.sub(r"\b(\w+)\.tla\b", lambda m: m[1] + (".tlaid" if m[1] in srcs else ".tla"), line)
        line = POS3.sub(lambda m: f"di baris {m[1]}, kolom {m[2]}", line)
        if line.startswith("Mengurai berkas"):
            if "jar:" in line or "/tlc-" in line:
                continue                                   # standard modules: noise
            m = re.search(r"/\.tlaid-out/(\w+)\.tla(?:id)?$", line)
            if m and m.group(1) not in srcs:
                continue                                   # TLA-ID wrapper modules: noise too
            line = re.sub(r"/\.tlaid-out/(\w+)\.tla(?:id)?$", r"/\1.tlaid", line)
        if any(line.startswith(n) for n in NOISE):
            continue
        m = re.match(r"^(Pemrosesan semantik|Pemeriksaan gaya) modul (\w+)$", line)
        if m and m.group(2) not in srcs:
            continue                                       # only your own modules are worth a line
        out.append(line)
    return "\n".join(out)

# ---------------------------------------------------------------- REPL
REPL_PROMPT = "(tla+) "
WRAPPER_NAMES = {idn: en for _, (_, ops) in STD.items() for en, idn in ops.items()}

def repl_expr_to_tla(expr):
    """One TLA-ID expression -> TLA+ for TLC's REPL (wrapper names back to the standard ones)."""
    tla, _ = to_tla(expr, "repl")
    out = []
    for toks in lex([tla]):
        out.append("".join(WRAPPER_NAMES.get(t[1], t[1]) if t[0] == "word" else t[1] for t in toks))
    return out[0].strip()

REPL_PHRASES = [
    ("tlc2.tool.EvalException: ", ""),
    ("TLC attempted to evaluate an unbounded \\A. Make sure that the expression is",
     "TLC mencoba mengevaluasi SEMUA tanpa batas. Pastikan ekspresinya"),
    ("TLC attempted to evaluate an unbounded CHOOSE. Make sure that the expression is",
     "TLC mencoba mengevaluasi PILIH tanpa batas. Pastikan ekspresinya"),
    ("of form \\A x \\in S: P(x).", "berbentuk SEMUA x DALAM S BERLAKU P(x)."),
    ("of form CHOOSE x \\in S: P(x).", "berbentuk PILIH x DALAM S SEHINGGA P(x)."),
    ("Attempted to compute cardinality of the value", "Mencoba menghitung kardinalitas dari nilai"),
    ("Could not find declaration or definition of symbol", "Tidak menemukan deklarasi atau definisi simbol"),
    ("Couldn't resolve infix operator symbol", "Tidak dapat mengenali simbol operator infiks"),
    ("parameters, but is applied to", "parameter, tetapi diterapkan pada"),
    ("is defined with", "didefinisikan dengan"),
    ("arguments.", "argumen."),
    ("Function '", "Fungsi '"),
    ("In applying the function", "Saat menerapkan fungsi"),
    ("the first argument is:", "argumen pertamanya:"),
    ("which is not in its domain.", "yang tidak ada dalam domainnya."),
    ("which is not in its", "yang tidak ada dalam"),
    ("Attempted to select nonexistent field", "Mencoba memilih field yang tidak ada,"),
    ("from the record", "dari record"),
    ("Attempted to access index", "Mencoba mengakses indeks"),
    ("which is out of bounds.", "yang di luar batas."),
    (" of tuple ", " dari tuple "),
    ("Attempted to evaluate a CASE with no conditions true.", "Mencoba mengevaluasi KASUS tanpa satu pun kondisi yang benar."),
    ("In computing next states, TLC encountered a CASE with no conditions true.",
     "Saat menghitung keadaan berikutnya, TLC menemukan KASUS tanpa satu pun kondisi yang benar."),
    ("should be an integer, but instead it is:", "seharusnya bilangan bulat, tetapi nilainya:"),
    ("The first argument of", "Argumen pertama"),
    ("but S was not enumerable.", "tetapi S tidak dapat dienumerasi."),
    ("Attempted to check if the value:", "Mencoba memeriksa apakah nilai"),
    ("Attempted to check if", "Mencoba memeriksa apakah"),
    ("which is not a TLC function value, is in the set of functions:", "yang bukan nilai fungsi TLC, termasuk dalam himpunan fungsi:"),
    ("is an element of the string", "adalah anggota string"),
    ("evaluated to FALSE; the second argument was:", "bernilai SALAH; argumen keduanya:"),
    ("Assert", "Tegaskan"),
    ("domain.", "domainnya."),
    ("Attempted to compute the value of an expression of form CHOOSE x \\in S: P,",
     "Mencoba menghitung nilai ekspresi berbentuk PILIH x DALAM S SEHINGGA P,"),
    ("but no element of S satisfied P.", "tetapi tidak ada anggota S yang memenuhi P."),
    ("Attempted to apply function:", "Mencoba menerapkan fungsi:"),
    ("which is not in the domain of the function.", "yang tidak ada dalam domain fungsi."),
    ("to argument", "ke argumen"),
    ("Attempted to apply Head to the empty sequence.", "Mencoba menerapkan Kepala pada barisan kosong."),
    ("Attempted to apply Tail to the empty sequence.", "Mencoba menerapkan Ekor pada barisan kosong."),
    ("TLC encountered the non-enumerable quantifier bound", "TLC menemukan batas kuantor yang tidak dapat dienumerasi:"),
    (" In TLA+, Seq(S) represents the set of all finite sequences whose elements come from the set S.",
     ". Di TLA+, Seq(S) (Barisan(S) di TLA-ID) adalah himpunan semua barisan berhingga yang elemennya berasal dari S."),
    (" Even when S is a finite set, the number of possible sequences in Seq(S) is unbounded because sequences can have any finite length (e.g., length 0, 1, 2, and so on).",
     " Walaupun S berhingga, banyaknya barisan di dalamnya tidak terbatas, karena panjang barisan boleh berapa saja (0, 1, 2, dan seterusnya)."),
    (" As a result, TLC cannot evaluate expressions that universally (\\A) or existentially (\\E) quantify over",
     " Karena itu TLC tidak bisa mengevaluasi SEMUA atau ADA yang berjalan atas"),
    (", because this would require checking an infinite number of cases.", ", karena itu berarti memeriksa kasus yang jumlahnya tak berhingga."),
    (" Note that for a finite set of sequences s, TLC handles s \\subseteq Seq(S).",
     " Untuk himpunan barisan s yang berhingga, TLC bisa menangani s BAGIAN DARI Barisan(S)."),
    (" See https://explain.tlapl.us/seq-unenumerable for additional details.", " Lihat https://explain.tlapl.us/seq-unenumerable untuk detailnya."),
    ("Attempted to check equality of integer", "Mencoba memeriksa kesamaan bilangan bulat"),
    ("with non-integer:", "dengan nilai yang bukan bilangan bulat:"),
]

TLAREPL_POS = re.compile(r",? ?\[?line \d+, col \d+ to line \d+, col \d+ of module tlarepl\]?")

def repl_translate(output, expr):
    lines = []
    for line in output.split("\n"):
        if line.startswith("Error evaluating expression: '"):
            lines.append(f"Kesalahan saat mengevaluasi ekspresi: '{expr}'"); continue
        line = TLAREPL_POS.sub("", line)               # positions inside the REPL's scratch module mean nothing to you
        if line.startswith("[") and not re.match(r"^\[\s*\w+\s*(\|->|:)", line) and line.rstrip().endswith("]") is False:
            line = line[1:]
        line = re.sub(r"\.\]$", ".", line)
        if not line.strip():
            continue
        if any(en in line for en, _ in REPL_PHRASES):
            for en, idn in REPL_PHRASES:
                line = line.replace(en, idn)
        line = POS1.sub(lambda m: f"baris {m[1]}, kolom {m[2]} sampai baris {m[3]}, kolom {m[4]}, modul {m[5]}", line)
        lines.append(translate_values(line))
    return "\n".join(lines)

class Repl:
    def __init__(self):
        self.p = subprocess.Popen(["java", "-cp", JAR, "tlc2.REPL"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=0)
        self._until_prompt()

    def _until_prompt(self):
        buf = ""
        while not buf.endswith(REPL_PROMPT):
            ch = self.p.stdout.read(1)
            if not ch:
                break
            buf += ch
        return buf[:-len(REPL_PROMPT)] if buf.endswith(REPL_PROMPT) else buf

    def ask(self, expr):
        try:
            tla = repl_expr_to_tla(expr)
        except TlaidError as e:
            return "Kesalahan TLA-ID: " + str(e).split(": ", 1)[-1]
        self.p.stdin.write(tla + "\n"); self.p.stdin.flush()
        return repl_translate(self._until_prompt().strip("\n"), expr)

def run_repl(path=None):
    r = Repl()
    src = open(path) if path else None
    if not src:
        print("REPL TLA-ID. Ketik ekspresi TLA-ID; Ctrl-D untuk keluar.")
    while True:
        if src:
            line = src.readline()
            if not line:
                break
            line = line.rstrip("\n")
            print("(tla-id) " + line)
        else:
            try:
                line = input("(tla-id) ")
            except EOFError:
                print(); break
        if line.strip():
            print(r.ask(line))
    r.p.kill()

# ---------------------------------------------------------------- driver
def build_folder(folder, outdir, target=None):
    """Transpile every .tlaid/.cfgid in folder. A broken file stops the run only if it is the target."""
    os.makedirs(outdir, exist_ok=True)
    shifts, srcs = {}, {}
    for f in sorted(os.listdir(folder)):
        p = os.path.join(folder, f)
        if f.endswith(".tlaid"):
            src = open(p).read()
            mod = f[:-6]
            try:
                tla, sh = to_tla(src, f)
            except TlaidError as e:
                if mod == target:
                    raise
                print(f"(dilewati: {e})", file=sys.stderr)
                continue
            open(os.path.join(outdir, mod + ".tla"), "w").write(tla)
            shifts[mod] = sh; srcs[mod] = src.split("\n")
        elif f.endswith(".cfgid"):
            open(os.path.join(outdir, f[:-6] + ".cfg"), "w").write(cfg_to_tla(open(p).read()))
    for name, text in wrapper_modules().items():
        open(os.path.join(outdir, name + ".tla"), "w").write(text)
    json.dump(shifts, open(os.path.join(outdir, "tlaid.map.json"), "w"))
    return shifts, srcs

def main(argv):
    if argv and argv[0] == "repl":
        run_repl(argv[1] if len(argv) > 1 else None); return 0
    if argv and argv[0] == "baru" and len(argv) > 1:
        base = argv[1]; name = os.path.basename(base)
        if os.path.exists(base + ".tlaid"):
            print(f"{base}.tlaid sudah ada"); return 1
        open(base + ".tlaid", "w").write(
            f"---- MODUL {name} ----\nMENGGUNAKAN BilanganAsli\n\nVARIABEL x\n\nInit == x = 0\n"
            f"Next == x' = x\n\nSpec == Init DAN SELALU [Next] ATAU STUTTERING x\n\nTypeOK == x DALAM Asli\n====\n")
        open(base + ".cfgid", "w").write("SPESIFIKASI Spec\nINVARIAN TypeOK\n")
        print(f"Dibuat: {base}.tlaid dan {base}.cfgid"); return 0
    if len(argv) < 2:
        print(__doc__); return 2
    cmd, path = argv[0], argv[1]
    if cmd == "tla":
        src = open(path).read()
        if path.endswith(".cfgid"):
            sys.stdout.write(cfg_to_tla(src))
        else:
            try:
                sys.stdout.write(to_tla(src, os.path.basename(path))[0])
            except TlaidError as e:
                print("Kesalahan TLA-ID:", e); return 1
        return 0
    if cmd == "impor":
        src = open(path).read()
        if path.endswith(".cfg"):
            sys.stdout.write(cfg_to_tlaid(src)); return 0
        renames = {}
        for std, (wrap, ops) in STD.items():
            if re.search(r"^\s*EXTENDS\b[^\n]*\b" + std + r"\b", src, re.M):
                renames[std] = wrap; renames.update(ops)
        sys.stdout.write(to_tlaid(src, renames)); return 0
    if cmd in ("cek", "urai"):
        folder = os.path.dirname(os.path.abspath(path))
        mod = os.path.basename(path)[:-6]
        outdir = os.path.join(folder, ".tlaid-out")
        try:
            shifts, srcs = build_folder(folder, outdir, mod)
        except TlaidError as e:
            print("Kesalahan TLA-ID:", e); return 1
        srcs = {mod: srcs[mod], **{k: v for k, v in srcs.items() if k != mod}}
        jopts = os.environ.get("JAVA_OPTS", "").split()       # e.g. JAVA_OPTS=-Dtlc2.tool.impl.Tool.cdot=true
        if cmd == "urai":
            args = ["java", *jopts, "-cp", JAR, "tla2sany.SANY", mod + ".tla"]
        else:
            extra = argv[2:] if "-workers" in argv[2:] else ["-workers", "1", *argv[2:]]
            args = ["java", "-XX:+UseParallelGC", *jopts, "-cp", JAR, "tlc2.TLC", "-metadir", "states",
                    "-config", mod + ".cfg", *extra, mod + ".tla"]
        r = subprocess.run(args, cwd=outdir, capture_output=True, text=True)
        print(translate_output(r.stdout + r.stderr, shifts, srcs))
        return r.returncode
    print(__doc__); return 2

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
